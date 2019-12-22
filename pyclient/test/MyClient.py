from common.phx_protocol import *
from common.phx_structs import *
from common.phx_definitions import *
from common.phx_trader_spi import CPhxFtdcTraderSpi
from common.phx_trader_api import CPhxFtdcTraderApi
from test.OrderManager import OrderManager
import time
import json
from collections import deque
from optparse import OptionParser
from random import randint, random
from test.OrderList import OrderList, OrderInfo, Snapshot
import threading
import copy
import signal


class MyClient(CPhxFtdcTraderSpi):
    def __init__(self):
        super().__init__()
        self.serverHost = '127.0.0.1'
        self.serverOrderPort = 0
        self.serverQryPort = 0
        self.serverRtnPort = 0
        self.serverMDPort = 0
        self.nRequestID = 0
        self.orderRef = 0
        self.m_Token = ''
        self.m_UserID = None
        self.m_Passwd = '123456'
        self.m_LoginStatus = [False, False, False, False]
        self.query_status = False
        self.is_any_updated = False
        self.game_status = None
        self.ins2om = {}
        self.ins2index = {}
        self.instruments = []
        self.md_list = []  # array of md deque
        self.inst_num = 0
        self.market_data_updated = []
        self._background = None
        self.m_pUserApi = CPhxFtdcTraderApi()
        self._is_background_started = False

        # parameters for marketing
        self.contract_name = ["050", "052", "054", "056", "058", "060", "062", "064", "066", "068", "070", "072", "074",
                              "076", "078", "080", "083", "086", "089", "092", "095", "098", "101", "104", "107", "110",
                              "114", "118", "122", "126", "130", "134", "138", "142", "146", "150"]
        self.contract_price = [0.50, 0.52, 0.54, 0.56, 0.58, 0.60, 0.62, 0.64, 0.66, 0.68, 0.70, 0.72, 0.74,
                               0.76, 0.78, 0.80, 0.83, 0.86, 0.89, 0.92, 0.95, 0.98, 1.01, 1.04, 1.07, 1.10,
                               1.14, 1.18, 1.22, 1.26, 1.30, 1.34, 1.38, 1.42, 1.46, 1.50]

        self.up_index = 0
        self.bottom_index = 0

        self.must_contract = set()

        self.ubiq = None
        self.ubiq_last_price = 10
        self.future_volume = 0
        self.debt_volume = 0


    def reset(self):
        """Reset function after each round"""
        for ins, om in self.ins2om.items():
            om.clear()
            self.md_list[self.ins2index[ins]].clear()
            self.market_data_updated[self.ins2index[ins]] = False

        self.is_any_updated = False

    def next_request_id(self):
        self.nRequestID += 1
        return self.nRequestID

    def next_order_ref(self):
        self.orderRef += 1
        return self.orderRef

    def OnFrontConnected(self):
        print("OnFrontConnected, Start to ReqUserLogin")
        self.ReqUserLogin()

    def ReqUserLogin(self):
        field = CPhxFtdcReqUserLoginField()
        field.UserID = self.m_UserID
        field.Password = self.m_Passwd
        ret = self.m_pUserApi.ReqUserLogin(field, PHX_LINK_TYPE_Order, self.next_request_id())
        print("ReqUserLogin Order (%s:%d) ret=%d" % (self.serverHost, self.serverOrderPort, ret))
        ret = self.m_pUserApi.ReqUserLogin(field, PHX_LINK_TYPE_Qry, self.next_request_id())
        print("ReqUserLogin Qry (%s:%d) ret=%d" % (self.serverHost, self.serverQryPort, ret))
        ret = self.m_pUserApi.ReqUserLogin(field, PHX_LINK_TYPE_Rtn, self.next_request_id())
        print("ReqUserLogin Rtn (%s:%d) ret=%d" % (self.serverHost, self.serverRtnPort, ret))
        ret = self.m_pUserApi.ReqUserLogin(field, PHX_LINK_TYPE_MD, self.next_request_id())
        print("ReqUserLogin MD (%s:%d) ret=%d" % (self.serverHost, self.serverMDPort, ret))

    def OnRspUserLogin(self, pRspUserLogin: CPhxFtdcRspUserLoginField, LinkType, ErrorID, nRequestID):
        print('OnRspUserLogin, data=%s, ErrorID=%d, ErrMsg=%s, nRequestID=%d' % (json.dumps(pRspUserLogin.__dict__), ErrorID, get_server_error(ErrorID), nRequestID))
        if ErrorID == 0:
            self.m_LoginStatus[LinkType] = True
            if pRspUserLogin.MaxOrderLocalID > self.orderRef:
                self.orderRef = pRspUserLogin.MaxOrderLocalID + 1

    def OnRspOrderInsert(self, pInputOrder: CPhxFtdcInputOrderField, ErrorID):
        if ErrorID != 0:
            print('OnRspOrderInsert, orderRef=%d, ErrorID=%d, ErrMsg=%s' % (pInputOrder.OrderLocalID, ErrorID, get_server_error(ErrorID)))
            if pInputOrder.InstrumentID not in self.ins2om:
                return
            om = self.ins2om[pInputOrder.InstrumentID]
            om.on_rsp_order_insert(pInputOrder.OrderLocalID)

    def OnRspOrderAction(self, pInputOrderAction: CPhxFtdcOrderActionField, ErrorID):
        if ErrorID != 0:
            print('OnRspOrderAction, orderRef=%d, ErrorID=%d, ErrMsg=%s' % (pInputOrderAction.OrderLocalID, ErrorID, get_server_error(ErrorID)))

    def OnRspQryTradingAccount(self, pTradingAccount: CPhxFtdcRspClientAccountField, ErrorID, nRequestID, bIsLast):
        print('OnRspQryTradingAccount, data=%s, ErrorID=%d, ErrMsg=%s, bIsLast=%d' % (json.dumps(pTradingAccount.__dict__), ErrorID, get_server_error(ErrorID), bIsLast))

    def OnRspQryInstrument(self, pInstrument: CPhxFtdcRspInstrumentField, ErrorID, nRequestID, bIsLast):
        # print('OnRspQryInstrument, data=%s, ErrorID=%d, bIsLast=%d' % (json.dumps(pInstrument.__dict__), ErrorID, bIsLast))
        if pInstrument.InstrumentID not in self.ins2om:
            self.ins2om[pInstrument.InstrumentID] = OrderManager(pInstrument.InstrumentID)
            self.md_list.append(deque(maxlen=10))
            self.instruments.append(copy.copy(pInstrument))
            self.market_data_updated.append(False)
            self.ins2index[pInstrument.InstrumentID] = self.inst_num
            self.inst_num += 1

        if bIsLast:
            self.query_status = True
            print("total %d instruments" % self.inst_num)

    def OnRtnGameStatus(self, pGameStatus: CPhxFtdcGameStatusField):
        # print('OnRtnGameStatus, data=%s' % json.dumps(pGameStatus.__dict__))
        self.game_status = pGameStatus

    def grid_strategy(self, gap=0.05, money=10000, lastprice=10, currentprice=10, limit=1000000):
        newgrid = int(abs(currentprice - lastprice) / gap)
        direction = PHX_FTDC_D_Buy if currentprice <= lastprice else PHX_FTDC_D_Sell
        # offset = PHX_FTDC_OF_Open if currentprice <= lastprice else PHX_FTDC_OF_Close
        
        if grid < newgrid:
            om = self.ins2om['UBIQ']
            volume = int(newgrid * money / currentprice)
            if direction == PHX_FTDC_D_Buy and self.debt < 0 and self.future_volume * currentprice < 1000000:
                offset = PHX_FTDC_OF_Open
            elif direction == PHX_FTDC_D_Buy and self.debt >= 0:
                offset = PHX_FTDC_OF_Close
                volume = self.debt
            elif direction == PHX_FTDC_D_Sell and self.future_volume > 0:
                offset = PHX_FTDC_OF_Close
                volume = min(self.future_volume, volume)
            elif direction == PHX_FTDC_D_Sell and self.debt_volume * currentprice < 1000000:
                offset = PHX_FTDC_OF_Open
            order = om.place_market_order(self.next_order_ref(), direction, offset, volume)
            return currentprice
        else:
            return lastprice

    def OnRtnMarketData(self, pMarketData: CPhxFtdcDepthMarketDataField):
        nowtime = time.time()
        market_data = pMarketData.__dict__
        if len(self.marketdatacol) == 0:
            self.marketdatacol = list(market_data.keys())
            self.marketdatacol.sort()
            self.market_data_log.write('timestamp,'+','.join(self.marketdatacol)+'\n')
        assert len(self.marketdatacol) == len(list(market_data.keys()))
        line = [str(nowtime)]
        for col in self.marketdatacol:
            line.append(str(market_data[col]))
        self.market_data_log.write(','.join(line)+'\n')


        if pMarketData.InstrumentID in self.ins2index:
            # print('OnRtnMarketData, data=%s' % json.dumps(pMarketData.__dict__))
            index = self.ins2index[pMarketData.InstrumentID]
            self.md_list[index].append(pMarketData)
            self.market_data_updated[index] = True
            self.is_any_updated = True

            if pMarketData.InstrumentID == 'UBIQ':
                self.debt_volume = self.ins2om['UBIQ'].get_short_position_closeable()
                self.future_volume = self.ins2om['UBIQ'].get_long_position_closeable()
                self.ubiq_last_price = self.grid_strategy(gap=0.05, money=100000, lastprice=self.ubiq_last_price,
                                                          currentprice=pMarketData.LastPrice, limit=1000000)

                

    def OnRtnOrder(self, pOrder: CPhxFtdcOrderField):
        if pOrder.InstrumentID not in self.ins2om:
            return
        om = self.ins2om[pOrder.InstrumentID]
        om.on_rtn_order(pOrder)

    def OnRtnTrade(self, pTrade: CPhxFtdcTradeField):
        # print('OnRtnTrade, data=%s' % json.dumps(pTrade.__dict__))
        if pTrade.InstrumentID not in self.ins2om:
            return
        om = self.ins2om[pTrade.InstrumentID]
        om.on_rtn_trade(pTrade)

    def OnErrRtnOrderInsert(self, pInputOrder: CPhxFtdcInputOrderField, ErrorID):
        if ErrorID != 0:
            print('OnErrRtnOrderInsert, orderRef=%d, ErrorID=%d, ErrMsg=%s' % (pInputOrder.OrderLocalID, pInputOrder.ExchangeErrorID, get_server_error(pInputOrder.ExchangeErrorID)))
            if pInputOrder.InstrumentID not in self.ins2om:
                return
            om = self.ins2om[pInputOrder.InstrumentID]
            om.on_rsp_order_insert(pInputOrder.OrderLocalID)

    def OnErrRtnOrderAction(self, pOrderAction: CPhxFtdcOrderActionField, ErrorID):
        if ErrorID != 0:
            print('OnErrRtnOrderAction, orderRef=%d, ErrorID=%d, ErrMsg=%s' % (pOrderAction.OrderLocalID, pOrderAction.ExchangeErrorID, get_server_error(pOrderAction.ExchangeErrorID)))

    def OnRspQryOrder(self, pOrder: CPhxFtdcOrderField, ErrorID, nRequestID, bIsLast):
        if pOrder is not None and ErrorID == 0:
            if pOrder.InstrumentID not in self.ins2om:
                return
            om = self.ins2om[pOrder.InstrumentID]
            om.insert_init_order(pOrder)
            om.on_rtn_order(pOrder)

        if bIsLast:
            self.query_status = True
            print("init order query over")

    def OnRspQryTrade(self, pTrade: CPhxFtdcTradeField, ErrorID, nRequestID, bIsLast):
        if pTrade is not None and ErrorID == 0:
            if pTrade.InstrumentID not in self.ins2om:
                return
            om = self.ins2om[pTrade.InstrumentID]
            om.on_rtn_trade(pTrade)

        if bIsLast:
            self.query_status = True
            print("init trade query over")

    def timeout_wait(self, timeout, condition=None):
        while timeout > 0:
            time.sleep(1)
            timeout -= 1
            if condition is None:
                if self.query_status:
                    return True
            elif isinstance(condition, list):
                if all(condition):
                    return True
        return False

    def Init(self):
        self.market_data_log = open("logs/market.csv", "w+")
        self.m_pUserApi.RegisterSpi(self)
        self.m_pUserApi.RegisterOrderFront(self.serverHost, self.serverOrderPort)
        self.m_pUserApi.RegisterQryFront(self.serverHost, self.serverQryPort)
        self.m_pUserApi.RegisterRtnFront(self.serverHost, self.serverRtnPort)
        self.m_pUserApi.RegisterMDFront(self.serverHost, self.serverMDPort)

        self.m_pUserApi.Init()
        if not self.timeout_wait(10, self.m_LoginStatus):
            return False

        print("OnRspUserLogin, all link ready")
        self.query_status = False
        ret = self.m_pUserApi.ReqQryInstrument(CPhxFtdcQryInstrumentField(), self.next_request_id())
        if (not ret) or (not self.timeout_wait(10)):
            print("ReqQryInstrument failed")
            return False

        self.query_status = False
        field = CPhxFtdcQryOrderField()
        field.InvestorID = self.m_UserID
        ret = self.m_pUserApi.ReqQryOrder(field, self.next_request_id())
        if (not ret) or (not self.timeout_wait(10)):
            print("ReqQryOrder failed")
            return False

        self.query_status = False
        field = CPhxFtdcQryTradeField()
        field.InvestorID = self.m_UserID
        ret = self.m_pUserApi.ReqQryTrade(field, self.next_request_id())
        if (not ret) or (not self.timeout_wait(10)):
            print("ReqQryTrade failed")
            return False

        self._is_background_started = True
        self._background = threading.Thread(target=self.background_thread)
        self._background.start()
        if not self.timeout_wait(10):
            return False
        return True

    def background_thread(self):
        print("start background thread")
        last_time = time.time()
        field = CPhxFtdcQryClientAccountField()
        while True:
            if not self._is_background_started:
                break
            t = time.time()
            if t - last_time > 5 and self.m_pUserApi.all_connected:
                last_time = t
                ret = self.m_pUserApi.ReqQryTradingAccount(field, self.next_request_id())
                if not ret:
                    print("ReqQryTradingAccount failed")
            time.sleep(0.5)

    def stop_all_threads(self):
        self.m_pUserApi.stop()
        self._is_background_started = False
        time.sleep(0.6)

    def random_direction(self):
        if randint(0, 1) == 0:
            return PHX_FTDC_D_Buy
        else:
            return PHX_FTDC_D_Sell

    def random_offset(self):
        if randint(0, 1) == 0:
            return PHX_FTDC_OF_Open
        else:
            return PHX_FTDC_OF_Close

    def send_input_order(self, order: OrderInfo):
        field = CPhxFtdcQuickInputOrderField()
        field.OrderPriceType = order.OrderPriceType
        field.OffsetFlag = order.OffsetFlag
        field.HedgeFlag = PHX_FTDC_HF_Speculation
        field.InstrumentID = order.InstrumentID
        field.Direction = order.Direction
        field.VolumeTotalOriginal = order.VolumeTotalOriginal
        field.TimeCondition = PHX_FTDC_TC_GFD
        field.VolumeCondition = PHX_FTDC_VC_AV
        if order.OrderPriceType == PHX_FTDC_OPT_LimitPrice:
            field.LimitPrice = order.LimitPrice
        field.OrderLocalID = order.OrderLocalID
        ret = self.m_pUserApi.ReqQuickOrderInsert(field, self.next_request_id())
        print("QuickOrderInsert ", field, ret)

    def send_cancel_order(self, order: OrderInfo):
        field = CPhxFtdcOrderActionField()
        field.OrderSysID = order.OrderSysID
        field.InvestorID = self.m_UserID
        field.OrderLocalID = order.OrderLocalID
        ret = self.m_pUserApi.ReqOrderAction(field, self.next_request_id())
        print("ActionOrder data=%s, ret=%d" % (json.dumps(field.__dict__), ret))

    def random_input_order(self, ins_idx):
        ins = self.instruments[ins_idx]
        om = self.ins2om[ins.InstrumentID]
        order = om.place_limit_order(self.next_order_ref(), self.random_direction(), self.random_offset(), random() * 20, 1)
        self.send_input_order(order)

    def random_cancel_order(self, ins_idx):
        ins = self.instruments[ins_idx]
        om = self.ins2om[ins.InstrumentID]
        bids, asks = om.get_untraded_orders()
        for order in bids:
            self.send_cancel_order(order)
        for order in asks:
            self.send_cancel_order(order)

    def run_strategy(self):
        # FOR_EACH_INSTRUMENT
        for i in range(self.inst_num):
            if randint(0, 5) == 1:
                self.random_input_order(i)
            if randint(0, 5) == 1:
                self.random_cancel_order(i)
            self.market_data_updated[i] = False  # reset flag

        self.is_any_updated = False  # reset flag

    def visualization(self):
        self.ubiq = self.ins2om['UBIQ']
        print('\n\n' + '-' * 100)
        print('| Future Volume ' + ' ' * 35 + ' | UBIQ' + ' ' * 41 + '|')
        for contract in self.must_contract:
            om = self.ins2om[contract]
            long = om.get_long_position_closeable()
            short = om.get_short_position_closeable()
            holding = om.get_current_net_holding_position()
            print(f'| long: {long} | short: {short} | holding: {holding} \n')
        print('| ' + '| CurPrice : %-10.6f | NetPrice: %-10.6f |'
              % (self.ubiq.AskPrice * self.ubiq.AskVolume, self.ubiq.BidPrice * self.ubiq.BidVolume))
        print('| ' + ' ' * 50 + '| BidVolume: %-10.6f | BidPrice: %-10.6f |'
              % (self.ubiq.BidVolume, self.ubiq.BidPrice * self.ubiq.BidVolume))
        print('| ' + ' ' * 50 + '| AskVolume: %-10.6f | AskPrice: %-10.6f |' % (self.ubiq.AskVolume, self.ubiq.AskPrice * self.ubiq.AskVolume))

        print('-' * 100)
        print('| ' + ' ' * 50 + '| PreBalance: %-10.6f | AskPrice: %-10.6f |' % (self.PreBalance, self.CurrMargin))
        print(
            '| ' + ' ' * 50 + '| FloatProfit: %-10.6f | CloseProfit: %-10.6f |' % (self.ubiq.AskVolume, self.ubiq.AskPrice))
        print('| ' + ' ' * 50 + '| Balance:    %-10.6f | Available: %-10.6f |' % (
        self.ubiq.AskVolume, self.ubiq.AskPrice * self.ubiq.AskVolume))
        print('| ' + ' ' * 50 + '| MarketCount: %-10.6f | TradeCount: %-10.6f |' % (
        self.ubiq.AskVolume, self.ubiq.AskPrice * self.ubiq.AskVolume))
        print('-' * 100)


if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option("-i", "--ip", dest="ip", help="server ip")
    parser.add_option("-p", "--port", dest="port", help="server ip")
    parser.add_option("-u", "--user_id", dest="user_id", help="user id")
    parser.add_option("-a", "--password", dest="password", help="password")
    (options, args) = parser.parse_args()
    server_ip = '106.120.131.90'
    order_port = 9000
    user_id = 49
    password = 'qd81CocT'

    if options.ip:
        server_ip = options.ip
    if options.port:
        order_port = int(options.port)
    if options.user_id:
        user_id = int(options.user_id)
    if options.password:
        password = options.password

    client = MyClient()
    client.serverHost = server_ip
    client.serverOrderPort = order_port
    client.serverRtnPort = order_port + 1
    client.serverQryPort = order_port + 2
    client.serverMDPort = order_port + 3
    client.m_UserID = user_id
    client.m_Passwd = password

    def _KeyboardInterruptHandler(signal, frame):
        print("KeyboardInterrupt (ID: {}) has been caught. Cleaning up...".format(signal))
        client.stop_all_threads()
        exit(0)

    signal.signal(signal.SIGINT, _KeyboardInterruptHandler)

    if client.Init():
        print("init success")
        resetted = True
        while True:
            if client.game_status is None or (not client.m_pUserApi.all_connected):
                print("server not started")
                time.sleep(1)
            elif client.game_status.GameStatus == 0:
                print("game not started, waitting for start")
                time.sleep(1)
            elif client.game_status.GameStatus == 1:
                resetted = False
                client.visualization()
                time.sleep(0.5)
            elif client.game_status.GameStatus == 2:
                print("game settling")
                time.sleep(1)
            elif client.game_status.GameStatus == 3:
                print("game settled, waiting for next round")
                if not resetted:
                    client.reset()
                    resetted = True
                    print("client resetted")
                time.sleep(1)
            elif client.game_status.GameStatus == 4:
                print("game finished")
                break
    else:
        print("init failed")




