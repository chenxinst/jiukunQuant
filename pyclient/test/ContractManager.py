
class ContractManager(object):
    def __init__(self, instrument_id_):
        self.instrument_id = instrument_id_
        self.LastPrice = 0  # 最新价, double
        self.LastVolume = 0  # 数量, int32_t
        self.ExchangeTime = 0  # 时间, int32_t
        self.InstrumentID = ""  # 合约代码, char[13]
        self.BidPrice1 = 0  # 申买价一, double
        self.BidVolume1 = 0  # 申买量一, int32_t
        self.AskPrice1 = 0  # 申卖价一, double
        self.AskVolume1 = 0  # 申卖量一, int32_t
        self.BidPrice2 = 0  # 申买价二, double
        self.BidVolume2 = 0  # 申买量二, int32_t
        self.AskPrice2 = 0  # 申卖价二, double
        self.AskVolume2 = 0  # 申卖量二, int32_t
        self.BidPrice3 = 0  # 申买价三, double
        self.BidVolume3 = 0  # 申买量三, int32_t
        self.AskPrice3 = 0  # 申卖价三, double
        self.AskVolume3 = 0  # 申卖量三, int32_t
        self.BidPrice4 = 0  # 申买价四, double
        self.BidVolume4 = 0  # 申买量四, int32_t
        self.AskPrice4 = 0  # 申卖价四, double
        self.AskVolume4 = 0  # 申卖量四, int32_t
        self.BidPrice5 = 0  # 申买价五, double
        self.BidVolume5 = 0  # 申买量五, int32_t
        self.AskPrice5 = 0  # 申卖价五, double
        self.AskVolume5 = 0  # 申卖量五, int32_t
