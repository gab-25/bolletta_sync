from abc import ABC


class BaseProvider(ABC):
    def get_invoices(self):
        """
        return the invoices from the provider
        """
        raise Exception("not implemented")
