"""最小の注文キャンセル実装。仕様上のBehaviorとの対応はrelation markerで表す。"""

from dataclasses import dataclass


@dataclass
class Order:
    paid: bool = False
    shipped: bool = False
    cancelled: bool = False
    refunded: bool = False


def cancel_order(order: Order) -> bool:
    """出荷前のみキャンセルし、決済済みなら返金状態にする。

    @relation(ORD-BEH-001, scope=function)
    @relation(ORD-BEH-002, scope=function)
    """
    if order.shipped or order.cancelled:
        return False

    order.cancelled = True
    if order.paid:
        order.refunded = True
    return True
