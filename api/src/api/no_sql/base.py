from abc import ABC, abstractmethod


class NoSQLDatabase(ABC):
    
    # @abstractmethod
    # def save_table(self, df, table_name, dataset_name, if_exists='append', to_str=False, merge_on=None, autodetect=False):
    #     pass

    @abstractmethod
    def save_response(responses, batch_size=200):
        pass