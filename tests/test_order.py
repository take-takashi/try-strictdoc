from src.order import Order, cancel_order


def test_cancel_unpaid_order():
    """未決済注文をキャンセル。

    @relation(ORD-SCN-001, scope=function)
    """
    order = Order(paid=False, shipped=False)

    assert cancel_order(order) is True
    assert order.cancelled is True
    assert order.refunded is False


def test_cancel_paid_order_and_refund():
    """決済済み注文をキャンセルして返金。

    @relation(ORD-SCN-002, scope=function)
    """
    order = Order(paid=True, shipped=False)

    assert cancel_order(order) is True
    assert order.cancelled is True
    assert order.refunded is True


def test_reject_cancel_for_shipped_order():
    """shipped=true の注文を拒否。

    @relation(ORD-SCN-003, scope=function)
    """
    order = Order(paid=True, shipped=True)

    assert cancel_order(order) is False
    assert order.cancelled is False
    assert order.refunded is False


def test_reject_cancel_for_already_cancelled_order():
    """キャンセル済み注文を再度キャンセルできない。

    @relation(ORD-SCN-004, scope=function)
    """
    order = Order(paid=False, shipped=False)

    assert cancel_order(order) is True
    assert order.cancelled is True

    assert cancel_order(order) is False
    assert order.cancelled is True
    assert order.refunded is False
