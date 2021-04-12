from decimal import Decimal
from typing import (
    Any,
    Dict,
    Optional,
)
import asyncio
from hummingbot.core.event.events import (
    OrderType,
    TradeType
)
from hummingbot.connector.in_flight_order_base import InFlightOrderBase


class BtseInFlightOrder(InFlightOrderBase):
    def __init__(self,
                 client_order_id: str,
                 exchange_order_id: Optional[str],
                 trading_pair: str,
                 order_type: OrderType,
                 trade_type: TradeType,
                 price: Decimal,
                 amount: Decimal,
                 initial_state: str = "OPEN"):
        super().__init__(
            client_order_id,
            exchange_order_id,
            trading_pair,
            order_type,
            trade_type,
            price,
            amount,
            initial_state,
        )
        self.trade_id_set = set()
        self.cancelled_event = asyncio.Event()

    # BTSE websocket: ORDER_INSERTED, TRIGGER_ACTIVATED, TRIGGER_INSERTED
    # BTSE Rest API "orderState": STATUS_ACTIVE
    # Unhandled States: "ORDER_PARTIALLY_TRANSACTED"
    # >>>>> NOTE: "ORDER_FULLY_TRANSACTED" becomes 'STATUS_INACTIVE' after 30 min
    @property
    def is_done(self) -> bool:
        return self.last_state in {"ORDER_FULLY_TRANSACTED"}

    @property
    def is_failure(self) -> bool:
        return self.last_state in {"ORDER_REJECTED", "INSUFFICIENT_BALANCE", "MARKET_UNAVAILABLE", "STATUS_INACTIVE"}

    @property
    def is_cancelled(self) -> bool:
        return self.last_state in {"ORDER_CANCELLED", "ORDER_NOTFOUND"}

    # @property
    # def order_type_description(self) -> str:
    #     """
    #     :return: Order description string . One of ["limit buy" / "limit sell" / "market buy" / "market sell"]
    #     """
    #     order_type = "market" if self.order_type is OrderType.MARKET else "limit"
    #     side = "buy" if self.trade_type == TradeType.BUY else "sell"
    #     return f"{order_type} {side}"

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> InFlightOrderBase:
        """
        :param data: json data from API
        :return: formatted InFlightOrder
        """
        retval = BtseInFlightOrder(
            data["client_order_id"],
            data["exchange_order_id"],
            data["trading_pair"],
            getattr(OrderType, data["order_type"]),
            getattr(TradeType, data["trade_type"]),
            Decimal(data["price"]),
            Decimal(data["amount"]),
            data["last_state"]
        )
        retval.executed_amount_base = Decimal(data["executed_amount_base"])
        retval.executed_amount_quote = Decimal(data["executed_amount_quote"])
        retval.fee_asset = data["fee_asset"]
        retval.fee_paid = Decimal(data["fee_paid"])
        retval.last_state = data["last_state"]
        return retval

    def update_with_trade_update(self, trade_update: Dict[str, Any]) -> bool:
        """
        Updates the in flight order with trade update (from private/get-order-detail end point)
        return: True if the order gets updated otherwise False
        """
        # trade_id = trade_update["orderID"]
        trade_id = str(trade_update["orderID"])
        print(f'\n\n >> update_with_trade_update: orderid: {trade_id}, self.exchange_order_id :{self.exchange_order_id}\n')
        print(f'\n trade_update: \t {trade_update} \n')
        print(f'\ntrade_id_set {self.trade_id_set}\n')
        print(f' fee amount in trade_update: {trade_update["feeAmount"]}')

        # TODO:  get trade_history in order to get feeAmount and feeCurrency
        # or trade_id in self.trade_id_set: # trade already recorded

        # params = {'orderID': trade_id}
        if trade_id != self.exchange_order_id:
            return False

        self.trade_id_set.add(str(trade_id))
        self.executed_amount_base += Decimal(str(trade_update["filledSize"]))
        self.fee_paid += Decimal(str(trade_update["feeAmount"]))

        self.executed_amount_quote += Decimal(str(trade_update['orderValue']))

        if not self.fee_asset:
            self.fee_asset = trade_update["feeCurrency"]
        return True
