import collections
import logging
import aiohttp
import asyncio
import inspect
import pandas as pd
from typing import Literal,List,Tuple
from typing import Callable
from dotenv import load_dotenv
from asyncio import Lock
import time

load_dotenv()

logger = logging.getLogger(__name__)

class RateLimitError(Exception):
    """Custom exception for rate limit errors."""

    def __init__(self, message="Rate limit exceeded. Please try again later."):
        self.message = message
        super().__init__(self.message)
class APIkeyError(Exception):
    """Custom exception for API key errors."""

    def __init__(self, message="API key is invalid or missing."):
        self.message = message
        super().__init__(self.message)
class NotFoundError(Exception):
    def __init__(self, message="404 Not found error"):
        self.message = message
        super().__init__(self.message)
class SkipItemException(Exception):
    def __init__(self, message="Skipping item due to error"):
        self.message = message
        super().__init__(self.message)


class ApiBase:
    """
    A class to simplify async API requests.
    """
    def __init__(self,
                 proxies : dict = None,
                 rate_limit_count : int = None,
                 rate_limit_period : int = None):
        """

        Args:
            logger_name (str): A name for the logger. Default 'ApiBase' if no name is given.
            logger (logging): A logger object. If left open, a default logger will be assigned.
            proxies (dict): A dictionary with proxies. Defaults to None. Example: proxies = {'http' : proxy_url_http, 'https' : proxy_url_https}
            rate_limit_count (int): Max number of requests for a given time period
            rate_limit_period (int): The time period in seconds for the rate limit

        """
        self.api_key = None
        self.session = None
        self.use_proxy = False
        self.proxies = proxies
        self.base_url = None
        self.ok_responses = 0
        self.fail_responses = 0
        self.rate_limit_count = rate_limit_count
        self.rate_limit_period = rate_limit_period
        self.request_timestamps = collections.deque()
        self._rate_limit_lock = Lock()


    def _ensure_fieldnames(self, df : pd.DataFrame) -> None:
        '''
        A function to ensure correct fieldnames of a pandas dataframe.
        The function changes the field names inplace.

        Args:
            df (pd.DataFrame): The dataframe you wish to ensure fieldnames on

        Returns:
            None
        '''
        new_cols = []
        for col in df.columns:
            new_cols.append(col.replace('.', '_', ))
        df.columns = new_cols

    def _mk_proxy(self, url: str) -> str:
        '''
        A function to choose the right proxy from the proxies dictionary.

        Args:
            url (str): The endpoint url in use

        Returns:
            proxy_url (str): The proxy url to use
        '''
        proxy_url = None
        if self.use_proxy:
            if url.startswith('https://'):
                proxy_url = self.proxies['https']
            else:
                proxy_url = self.proxies['http']
        return proxy_url

    async def _ensure_session(self) -> None:
        '''
        A function to ensure the session is active and running.
        The function updates the class attribute `.session` when called.

        Returns:
            None
        '''
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def _wait_for_rate_limit(self):
        """Sjekker og venter om rate limit er nådd, basert på et glidende vindu."""
        if not self.rate_limit_count:
            return

        async with self._rate_limit_lock:
            now = time.monotonic()

            while self.request_timestamps:
                if self.request_timestamps[0] < now - self.rate_limit_period:
                    self.request_timestamps.popleft()
                else:
                    break

            if len(self.request_timestamps) >= self.rate_limit_count:
                oldest_timestamp = self.request_timestamps[0]
                wait_time = oldest_timestamp - (now - self.rate_limit_period)

                if wait_time > 0:
                    logger.info(f"⏳ Rate limit reached — waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)

            self.request_timestamps.append(time.monotonic())

    async def close(self) -> None:
        '''
        A function to close the session.

        Returns:
            None
        '''
        if self.session and not self.session.closed:
            await self.session.close()
            # aiohttp requires one event-loop iteration after close() to release
            # underlying TCP connections. Without this the process hangs on exit.
            await asyncio.sleep(0.250)

    async def _reset_session(self):
        '''
        A function to reset the session.

        Returns:
            None
        '''
        if self.session:
            await self.session.close()
            await asyncio.sleep(0.250)
        self.session = None
        return await self._ensure_session()

    async def fetch_single(self, url : str,
                           headers : dict = None,
                           params : dict = None,
                           auth = None,
                           proxy_url : str = None,
                           timeout : int = 60,
                           allow_redirects: bool = True,
                           ssl: bool = True,
                           return_format: Literal["json", "txt"] = "json",
                           response_handler : Callable = None
                           ):
        '''
        Async method to fetch a given url.

        Args:
            url (str): The url to fetch
            headers (dict): Header. Example {'User-Agent': 'YourApp/1.0'}
            proxy_url (str): The proxy url to use
            params (dict): Dictionary of query parameters to add to the URL.
            auth (aiohttp.BasicAuth): Basic authentication credentials.
            timeout (int): The maximum number of seconds for the request to complete.
            allow_redirects (bool): If set to False, don't follow redirects.
            ssl (bool): Perform SSL verification. Set to False to ignore SSL certificate validation errors.
            return_format (Literal["json","txt"]): The format to return the response in. Can be "json" or "txt".
                                                   Defaults to "json".
            response_handler (callable): An optional async function to handle the aiohttp.ClientResponse object directly.
                                         If provided, `return_format` is ignored.
        Returns:


        Raises:
            RateLimitError: If the rate limit is exceeded.
            APIkeyError: If the API key is invalid or missing.
        '''
        await self._ensure_session()
        try:
            async with self.session.get(url,
                                        headers=headers,
                                        params = params,
                                        auth = auth,
                                        proxy=proxy_url,
                                        timeout = timeout,
                                        allow_redirects = allow_redirects,
                                        ssl = ssl) as response:
                #print(f"CODE: {response.status}\nRESPONSE: {response.json}\nURL: {url}\nHEADERS: {headers}")
                if response.status == 429:
                    error_message = await response.text()
                    raise RateLimitError(f'Rate limit exceeded. Error: {error_message}')
                elif response.status == 401:
                    error_message = await response.text()
                    raise APIkeyError(f'Authorization error. Error: {error_message}')
                elif response.status == 403:
                    error_message = await response.text()
                    raise PermissionError(f'Permission denied. Error: {error_message}')
                elif response.status == 404:
                    error_message = await response.text()
                    #logger.error(f'Error message - {inspect.currentframe().f_code.co_name}: {response.status}, {error_message}. URL: {url}')
                    raise NotFoundError(f'Not Found Error. Error message {error_message}')
                elif response.status == 500:
                    error_message = await response.text()
                    raise SkipItemException(f'Skip Item Exception. Error message {error_message}')
                elif response.status == 204:
                    error_message = await response.text()
                    raise NotFoundError(f'Not Found Error. Error code 204 - {error_message}')
                elif response.status == 400:
                    error_message = await response.text()
                    raise NotFoundError(f'Not Found Error. Error code 400 - {error_message}')
                elif response.status == 200:
                    if response_handler:
                        return await response_handler(response)
                    elif return_format:
                        if return_format == 'json':
                            response = await response.json()
                            return response
                        elif return_format == 'txt':
                            response = await response.text()
                            return response
                        else:
                            raise TypeError(f'return_format must be either json or txt but got {return_format}')
                    else:
                        raise TypeError(f'Either return_format or response_handler must be present.')
                else:
                    error_text = await response.text()
                    logger.error(
                        f'Error message - {inspect.currentframe().f_code.co_name}: {response.status}, {error_text}.')
                    response.raise_for_status()
        except (aiohttp.ClientError, aiohttp.ClientResponseError,asyncio.TimeoutError,ConnectionError) as e:
            logger.error(f"Network failure or timeout - {e}. url {url}. Doing a short timeout of 2 seconds")
            await asyncio.sleep(2)
            raise SkipItemException

    async def _process_tasks(self,tasks : list,
                             transformer : Callable[[List],any],
                             saver : Callable, save_interval : int) -> list:
        """
        A function to process a list of tasks.

        Args:
            tasks (list): The list of tasks to be processed
            save (bool): A boolean parameter to decide to save the data or not.
            save_interval (int): The interval at which to save the data.

        Returns:
            all_results (list): The list of all results.
        """

        all_results = []
        results_to_save = []
        task_futures = asyncio.as_completed(tasks)
        count = 0
        try:
            for future in task_futures:
                try:
                    result = await future
                    count += 1
                    self.ok_responses += 1 if result else 0
                    self.fail_responses += 1 if not result else 0

                    results_to_save.append(result)
                    if count % 500 == 0:
                        logger.info(f"🔄 Processed {count} items | ✅ {self.ok_responses} ok | ❌ {self.fail_responses} failed")

                    if len(results_to_save) >= save_interval:
                        logger.info(f"💾 Save interval reached at {count} items")
                        if saver:
                            try:
                                logger.info(f"📤 Saving {len(results_to_save)} results...")
                                data_to_save = await asyncio.to_thread(transformer,results_to_save)
                                await asyncio.to_thread(saver,data_to_save)
                            except Exception as e:
                                logger.error(f"❌ Save error: {e}")
                                raise
                        all_results.extend(results_to_save)
                        results_to_save.clear()
                except (RateLimitError, APIkeyError, PermissionError) as fatal_errors:
                    logger.error(f"❌ Fatal error in _process_tasks — stopping: {fatal_errors}")
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks,return_exceptions=True)
                    raise
                except SkipItemException as item_error:
                    logger.warning(f"⚠️ Skipping item (recoverable): {item_error}")
                    self.fail_responses += 1
                    continue
                except Exception as e:
                    logger.error(f"❌ Unexpected error in task loop: {e}")
                    self.fail_responses += 1
                    continue

        finally:
            if results_to_save:
                if saver:
                    try:
                        data_to_save = await asyncio.to_thread(transformer, results_to_save)
                        await asyncio.to_thread(saver, data_to_save)
                    except Exception as e:
                        logger.error(f"❌ Error saving final results: {e}")
                all_results.extend(results_to_save)
                results_to_save.clear()

        logger.info(f"✅ Job finished | ✅ {self.ok_responses} ok | ❌ {self.fail_responses} failed")
        return all_results

    async def get_items_with_ids(self,
                               inputs : list | dict,
                               fetcher : Callable,
                               transformer : Callable[[List],any],
                               saver : Callable = None,
                               save_interval: int = 50000,
                               concurrent_requests : int = 5,
                               return_result : bool = False,
                               ) -> list:
        """
        Fetches multiple items concurrently, associating each result with a unique ID.

        This function is designed to handle a list or dictionary of inputs, where each input
        can be uniquely identified. It uses asyncio.Semaphore to limit the number of
        concurrent requests to prevent overwhelming the API.

        Args:
            inputs (list | dict): A list of items or a dictionary where keys are item IDs
                                   and values are the items to be fetched.
            fetcher (callable): An asynchronous function that takes a single item as input and fetches its data.
            transformer (callable): A function to transform the results. NB: Must take a list as input!
            saver (callable): A function to save the results. Optional, if not provided, data will not be saved.
            save_interval (int): The number of results to accumulate before saving (if `save` is True).
            concurrent_requests (int): The maximum number of concurrent API requests.

        Returns:
            list: A list of tuples, where each tuple contains (item_id, result).
                  `result` will be None if an error occurred during fetching for that item.

        Raises:
            TypeError: If `inputs` is not a list or a dictionary.
            RateLimitError: Propagated from `_fetch_single` if a rate limit is encountered.
        """


        if isinstance(inputs, list):
            inputs = {addr : addr for addr in inputs}
        elif isinstance(inputs, dict):
            pass
        else:
            raise TypeError(f'Invalid input type. Expected list or dict, but got {type(inputs)}')

        semaphore = asyncio.Semaphore(concurrent_requests)

        async def fetch_item_with_id(item_id, item):
            """
            Takes in both an item_id and address.
            Args:
                item_id (str):
                address (str):

            Returns (tuple): (item_id, result)

            """
            await self._wait_for_rate_limit()
            async with semaphore:
                try:
                    result  = await fetcher(item)
                    return (item_id, result)
                except (RateLimitError, APIkeyError, PermissionError) as fatal_errors:
                    logger.error(f"❌ Fatal error for item_id={item_id}: {fatal_errors}")
                    raise
                # except (asyncio.TimeoutError, ConnectionError,aiohttp.ClientError,SkipItemException) as timeout_errors:
                #     logger.warning(f'Timeout errors with {item_id},{item} - {timeout_errors}')
                #     raise
                except SkipItemException as timeout_errors:
                    logger.warning(f"⚠️ Skipping item_id={item_id} due to timeout/connection error")
                    raise
                except Exception as e:
                    logger.error(f"❌ Error fetching item_id={item_id}: {e}")
                    return (item_id, None)

        tasks = [asyncio.create_task(fetch_item_with_id(item_id=item_id, item=item)) for item_id,item in inputs.items()]

        all_results = await self._process_tasks(tasks = tasks, transformer = transformer, saver = saver, save_interval=save_interval)
        if return_result:
            output = transformer(all_results)
            return output

    async def get_items(self,
                               inputs : list | dict,
                               fetcher : Callable,
                               transformer : Callable[[List],any],
                               saver : Callable = None,
                               save_interval: int = 50000,
                               concurrent_requests : int = 5,
                               return_result: bool = False,
                               ) -> list:
        """
        Fetches multiple items concurrently.

        This function is designed to handle a list of inputs. It uses asyncio.Semaphore
        to limit the number of concurrent requests to prevent overwhelming the API and to ensure fair usage.

        Args:
            inputs (list): A list of items to be fetched.
            fetcher (callable): An asynchronous function that takes a single item as input and fetches its data.
            transformer (callable): A function to transform the results. NB: Must take a list as input!
            saver (callable): A function to save the results. Optional, if not provided, data will not be saved.
            save_interval (int): The number of results to accumulate before saving (if `save` is True).
            concurrent_requests (int): The maximum number of concurrent API requests.

        Returns:
            list: A list of results. `None` will be included in the list if an error
                  occurred during fetching for that item.

        Raises:
            TypeError: If `inputs` is not a list.
            RateLimitError: Propagated from `_fetch_single` if a rate limit is encountered.
        """


        if not isinstance(inputs, list):
            raise TypeError(f'Invalid input type. Expected list, but got {type(inputs)}')

        semaphore = asyncio.Semaphore(concurrent_requests)

        async def fetch_item(item):
            await self._wait_for_rate_limit()
            async with semaphore:
                try:
                    result  = await fetcher(item)
                    return result
                except (RateLimitError, APIkeyError, PermissionError) as fatal_errors:
                    logger.error(f"❌ Fatal error for item={item}: {fatal_errors}")
                    raise
                # except (asyncio.TimeoutError, ConnectionError, aiohttp.ClientError) as timeout_errors:
                #     logger.warning(f'Timeout errors with {item} - {timeout_errors}')
                #     raise
                except SkipItemException as timeout_errors:
                    logger.warning(f"⚠️ Skipping item due to timeout/connection error: {item}")
                    raise
                except Exception as e:
                    logger.error(f"❌ Error fetching item={item}: {e}")
                    return None

        tasks = [asyncio.create_task(fetch_item(item=item)) for item in inputs]

        all_results = await self._process_tasks(tasks=tasks, transformer=transformer, saver=saver,save_interval=save_interval)
        if return_result:
            output = transformer(all_results)
            return output
