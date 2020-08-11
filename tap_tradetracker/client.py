from suds.plugin import MessagePlugin
from suds.client import Client

import singer

WSDL_URL = 'https://ws.tradetracker.com/soap/merchant?wsdl'
LOGGER = singer.get_logger()


class SoapFixer(MessagePlugin):
    def marshalled(self, context):
        pass


def basic_sobject_to_dict(obj):
    """Converts suds object to dict very quickly.
    Does not serialize date time or normalize key case.
    :param obj: suds object
    :return: dict object
    """
    if not hasattr(obj, '__keylist__'):
        return obj
    data = {}
    fields = obj.__keylist__
    for field in fields:
        val = getattr(obj, field)
        if isinstance(val, list):
            data[field] = []
            for item in val:
                data[field].append(basic_sobject_to_dict(item))
        else:
            data[field] = basic_sobject_to_dict(val)
    return data


def sobject_to_dict(obj, key_to_lower=False, json_serialize=False):
    """
    Converts a suds object to a dict.
    :param json_serialize: If set, changes date and time types to iso string.
    :param key_to_lower: If set, changes index key name to lower case.
    :param obj: suds object
    :return: dict object
    """
    import datetime

    if not hasattr(obj, '__keylist__'):
        if json_serialize and isinstance(obj, (datetime.datetime, datetime.time, datetime.date)):
            LOGGER.info(f'datetime: {obj}')
            return obj.isoformat()
        else:
            return obj
    data = {}
    fields = obj.__keylist__
    for field in fields:
        val = getattr(obj, field)
        if key_to_lower:
            field = field.lower()
        if isinstance(val, list):
            data[field] = []
            for item in val:
                data[field].append(sobject_to_dict(item, json_serialize=json_serialize))
        elif isinstance(val, (datetime.datetime, datetime.time, datetime.date)):
            data[field] = val.isoformat()
        else:
            data[field] = sobject_to_dict(val, json_serialize=json_serialize)
    return data


class TradeTrackerClient:
    def __init__(self,
                 customer_id,
                 passphrase,
                 sandbox=False,
                 locale=None,
                 demo=False):
        self.__customer_id = customer_id
        self.__passphrase = passphrase
        self.sandbox = sandbox
        self.locale = locale
        self.demo = demo
        self.__client = None

    def __enter__(self):
        self.__client = Client(WSDL_URL, plugins=[SoapFixer()])
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        pass

    def authenticate(self):
        self.__client.service.authenticate(customerID=self.__customer_id,
                                           passphrase=self.__passphrase,
                                           sandbox=self.sandbox,
                                           locale=self.locale,
                                           demo=self.demo)

    def get_campaigns(self) -> [dict]:
        campaigns = self.__client.service.getCampaigns()
        result = []
        for i in range(0, len(campaigns)):
            campaign = campaigns[i]
            result.append(sobject_to_dict(campaign))
        return result

    def get_affiliate_sites(self, campaign_id) -> [dict]:
        filter_options = self.__client.factory.create('AffiliateSiteFilter')
        affiliate_sites = self.__client.service.getAffiliateSites(campaign_id, filter_options)
        result = []
        for i in range(0, len(affiliate_sites)):
            affiliate_site = affiliate_sites[i]
            result.append(sobject_to_dict(affiliate_site))
        return result

    def get_report_campaign(self, campaign_id, date_from, date_to) -> dict:
        filter_options = self.__client.factory.create('ReportCampaignFilter')
        LOGGER.info(f'date_from={date_from} date_to={date_to}')
        filter_options.dateFrom = date_from
        filter_options.dateTo = date_to
        report_data = self.__client.service.getReportCampaign(campaignID=campaign_id, options=filter_options)
        return sobject_to_dict(report_data)
