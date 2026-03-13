import pytest
import pandas as pd
from api import ApiBase, RateLimitError, APIkeyError, SkipItemException
import asyncio
import time



# En konkret implementering av ApiBase for testing
class MockApiClient(ApiBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_url = "http://mockapi.com"
        self.saved_results = []

    async def get_item(self, item_id):
        url = f"{self.base_url}/items/{item_id}"
        # Her bruker vi headers-parameteren, ikke params
        return await self.fetch_single(url, headers={"X-Test": "true"})

    def transform_single(self, output):
        if output:
            id_str = output[0]
            data = output[1]
            return {"id": id_str, "data": data}
        return None

    def transform_output(self,outputs):
        return [self.transform_single(output) for output in outputs]

    def transform_output_lists(self,outputs):
        df = pd.DataFrame(outputs)
        return df

    def save_func(self, results):
        self.saved_results.extend(results)


@pytest.fixture
def client():
    """Pytest fixture for å lage en ny klient for hver test."""
    return MockApiClient()


# --- Synkrone tester ---

def test_ensure_fieldnames(client):
    """Tester at punktum i DataFrame-kolonner blir byttet ut med underscore."""
    df = pd.DataFrame({"user.id": [1], "user.name": ["Test"]})
    client._ensure_fieldnames(df)
    assert list(df.columns) == ["user_id", "user_name"]


def test_mk_proxy(client):
    """Tester at riktig proxy blir valgt basert på URL."""
    client.proxies = {"http": "http://proxy.example.com", "https": "https://proxy.example.com"}
    client.use_proxy = True
    assert client._mk_proxy("https://secure.com") == "https://proxy.example.com"
    assert client._mk_proxy("http://insecure.com") == "http://proxy.example.com"
    client.use_proxy = False
    assert client._mk_proxy("https://secure.com") is None


# --- Asynkrone tester ---

@pytest.mark.asyncio
async def test_session_management(client):
    """Tester at aiohttp-sesjonen blir opprettet og lukket korrekt."""
    await client._ensure_session()
    assert client.session is not None and not client.session.closed
    await client.close()
    assert client.session.closed


@pytest.mark.asyncio
async def test_reset_session(client):
    """Tester at sesjonen kan nullstilles."""
    await client._ensure_session()
    old_session = client.session
    await client._reset_session()
    assert old_session.closed
    assert client.session is not None and not client.session.closed
    await client.close()


@pytest.mark.asyncio
async def test_fetch_single_success(client, aresponses):
    """Tester en vellykket API-forespørsel (status 200)."""
    aresponses.add("mockapi.com", "/items/1", "GET", {"id": 1, "data": "original"})
    result = await client.get_item(1)
    assert result == {"id": 1, "data": "original"}
    await client.close()


@pytest.mark.asyncio
async def test_fetch_single_rate_limit_error(client, aresponses):
    """Tester at RateLimitError blir hevet ved status 429."""
    aresponses.add("mockapi.com", "/items/1", "GET", aresponses.Response(status=429))
    with pytest.raises(RateLimitError):
        await client.get_item(1)
    await client.close()


@pytest.mark.asyncio
async def test_fetch_single_apikey_error(client, aresponses):
    """Tester at APIkeyError blir hevet ved status 401."""
    aresponses.add("mockapi.com", "/items/1", "GET", aresponses.Response(status=401))
    with pytest.raises(APIkeyError):
        await client.get_item(1)
    await client.close()


@pytest.mark.asyncio
async def test_fetch_single_permission_error(client, aresponses):
    """Tester at PermissionError blir hevet ved status 403."""
    aresponses.add("mockapi.com", "/items/1", "GET", aresponses.Response(status=403))
    with pytest.raises(PermissionError):
        await client.get_item(1)
    await client.close()


@pytest.mark.asyncio
async def test_fetch_single_other_error(client, aresponses):
    """Tester håndtering av andre HTTP-feil (f.eks. 500)."""
    aresponses.add("mockapi.com", "/items/1", "GET", aresponses.Response(status=500))
    with pytest.raises(SkipItemException):
        await client.get_item(1)
    await client.close()


@pytest.mark.asyncio
async def test_get_items_with_ids(client, aresponses):
    """Tester henting av flere elementer med ID-er."""
    aresponses.add("mockapi.com", "/items/1", "GET", {"answer": 1})
    aresponses.add("mockapi.com", "/items/2", "GET", {"answer": 2})
    aresponses.add("mockapi.com", "/items/3", "GET", aresponses.Response(status=500))

    inputs = {"item1": "1", "item2": "2", "item3": "3"}
    results = await client.get_items_with_ids(inputs = inputs,
                                              fetcher = client.get_item,
                                              transformer = client.transform_output,
                                              saver = client.save_func,
                                                concurrent_requests=2,
                                              return_result=True)

    assert isinstance(results[0], dict)
    assert isinstance(results,list)
    assert isinstance(results[0].get("id"),str)
    await client.close()


@pytest.mark.asyncio
async def test_get_items(client, aresponses):
    """Tester henting av flere elementer fra en liste."""
    aresponses.add("mockapi.com", "/items/a", "GET", {"id": "a"})
    aresponses.add("mockapi.com", "/items/b", "GET", {"id": "b"})

    inputs = ["a", "b"]
    # get_items forventer en liste av tupler (item_id, item) i din implementering
    # Hvis den skal ta en ren liste, må du justere `tasks`-listen i get_items-metoden.
    # Gitt din nåværende kode, sender vi en liste med tupler:
    #tasks = [(item, item) for item in inputs]
    results = await client.get_items(inputs = inputs,
                                     fetcher = client.get_item,
                                     transformer=client.transform_output_lists,
                                     saver = client.save_func,
                                     return_result=True)


    assert len(results) == 2
    assert isinstance(results,pd.DataFrame)
    assert "id" in results.columns
    await client.close()

@pytest.mark.asyncio
async def test_save_func_integration(client, aresponses):
    """Tester at save_func blir kalt med riktig intervall."""
    for i in range(1, 7):  # 6 elementer
        aresponses.add("mockapi.com", f"/items/{i}", "GET", {"id": i})

    inputs = [str(i) for i in range(1, 7)]

    # Lagre hvert 3. resultat
    await client.get_items_with_ids(inputs = inputs,
                                    fetcher = client.get_item,
                                    transformer = client.transform_output,
                                    saver = client.save_func,
                                    save_interval=3,
                                    return_result=True)

    assert len(client.saved_results) == 6
    await client.close()

@pytest.mark.asyncio
async def test_get_items_with_ids_cancels_on_fatal_error(client, aresponses):
    """
    Tester at pågående oppgaver blir kansellert når en fatal feil (RateLimitError) oppstår.
    """
    completed_requests = []

    # 1. Simulerer en treg, vellykket forespørsel.
    #    Den skal sove i 1 sekund før den svarer.
    async def handler_slow_success(request):
        await asyncio.sleep(1)
        completed_requests.append("slow_success")
        return aresponses.Response(status=200, body='{"id": "slow"}')

    # 2. Denne vil utløse feilen umiddelbart.
    aresponses.add("mockapi.com", "/items/rate_limit_trigger", "GET", aresponses.Response(status=429))

    # 3. Denne er også treg og skal ALDRI fullføre, fordi den blir kansellert.
    async def handler_should_be_cancelled(request):
        await asyncio.sleep(1)
        completed_requests.append("should_be_cancelled") # Denne linjen skal aldri nås
        return aresponses.Response(status=200, body='{"id": "cancelled"}')

    aresponses.add("mockapi.com", "/items/slow_success", "GET", handler_slow_success)
    aresponses.add("mockapi.com", "/items/should_be_cancelled", "GET", handler_should_be_cancelled)

    inputs = {
        "req1": "slow_success",
        "req2": "rate_limit_trigger",
        "req3": "should_be_cancelled"
    }

    # Vi forventer at hele operasjonen feiler med RateLimitError
    with pytest.raises(RateLimitError):
        await client.get_items_with_ids(
            inputs=inputs,
            fetcher=client.get_item,
            transformer=client.transform_output,
            saver=client.save_func,
            concurrent_requests=3 # Kjører alle samtidig
        )

    # Nå sjekker vi hva som faktisk skjedde.
    # Vent litt for å sikre at event-loopen har håndtert kanselleringene.
    await asyncio.sleep(0.1)

    print(f"Fullførte forespørsler: {completed_requests}")
    assert "should_be_cancelled" not in completed_requests

    await client.close()


@pytest.mark.asyncio
async def test_rate_limiter_pauses_execution(aresponses):
    """
    Verifies if ratelimit works
    """
    client = MockApiClient(rate_limit_count=3, rate_limit_period=0.5)

    num_requests = 4
    inputs = [str(i) for i in range(1, num_requests + 1)]

    for i in inputs:
        aresponses.add("mockapi.com", f"/items/{i}", "GET", {"id": i})

    start_time = time.monotonic()

    results = await client.get_items(
        inputs=inputs,
        fetcher=client.get_item,
        transformer=client.transform_output_lists,
        concurrent_requests=num_requests,
        return_result=True
    )

    end_time = time.monotonic()
    duration = end_time - start_time

    print(f"Total tid for {num_requests} forespørsler: {duration:.4f} sekunder.")
    assert duration > client.rate_limit_period

    # Sjekk også at vi faktisk fikk alle resultatene til slutt
    assert len(results) == num_requests

    await client.close()