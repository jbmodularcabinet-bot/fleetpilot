"""Server-owned action vocabulary and detailed-to-owner status projection."""

FLOW = (
    "SCHEDULED",
    "DISPATCHED",
    "EN_ROUTE_TO_PICKUP",
    "ARRIVED_PICKUP",
    "LOADING_STARTED",
    "LOADING_COMPLETED",
    "DEPARTED_PICKUP",
    "EN_ROUTE_TO_DELIVERY",
    "ARRIVED_DELIVERY",
    "UNLOADING_STARTED",
    "UNLOADING_COMPLETED",
    "DELIVERED",
    "COMPLETED",
)
STATUS = {
    "SCHEDULED": "SCHEDULED",
    "DISPATCHED": "DISPATCHED",
    "EN_ROUTE_TO_PICKUP": "PICKUP",
    "ARRIVED_PICKUP": "PICKUP",
    "LOADING_STARTED": "PICKUP",
    "LOADING_COMPLETED": "LOADED",
    "DEPARTED_PICKUP": "IN_TRANSIT",
    "EN_ROUTE_TO_DELIVERY": "IN_TRANSIT",
    "ARRIVED_DELIVERY": "IN_TRANSIT",
    "UNLOADING_STARTED": "IN_TRANSIT",
    "UNLOADING_COMPLETED": "IN_TRANSIT",
    "DELIVERED": "DELIVERED",
    "COMPLETED": "COMPLETED",
    "CANCELLED": "CANCELLED",
}
# A departure confirms both physical departure and beginning the delivery leg.
ACTIONS = {
    "dispatch": ("SCHEDULED", ("DISPATCHED",), "Dispatch trip"),
    "start_pickup": ("DISPATCHED", ("EN_ROUTE_TO_PICKUP",), "Start / en route to pickup"),
    "arrive_pickup": ("EN_ROUTE_TO_PICKUP", ("ARRIVED_PICKUP",), "Arrived at pickup"),
    "start_loading": ("ARRIVED_PICKUP", ("LOADING_STARTED",), "Start loading"),
    "finish_loading": ("LOADING_STARTED", ("LOADING_COMPLETED",), "Loading complete"),
    "depart_pickup": (
        "LOADING_COMPLETED",
        ("DEPARTED_PICKUP", "EN_ROUTE_TO_DELIVERY"),
        "Depart pickup",
    ),
    "arrive_delivery": ("EN_ROUTE_TO_DELIVERY", ("ARRIVED_DELIVERY",), "Arrived at delivery"),
    "start_unloading": ("ARRIVED_DELIVERY", ("UNLOADING_STARTED",), "Start unloading"),
    "finish_unloading": ("UNLOADING_STARTED", ("UNLOADING_COMPLETED",), "Unloading complete"),
    "deliver": ("UNLOADING_COMPLETED", ("DELIVERED",), "Mark delivered"),
}
TERMINAL = {"COMPLETED", "CANCELLED"}


def next_action(milestone):
    return next((key for key, (before, _, _) in ACTIONS.items() if before == milestone), None)
