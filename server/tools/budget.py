MEAL_PER_DAY = {"早餐": 15, "午餐": 45, "晚餐": 60}
CITY_TRANSIT_PER_DAY = 35


def budget(days, tickets_total, intercity_price=0, family=False):
    """budget 工具：预算核算。餐饮亲子模式上浮（加儿童餐与零食）。"""
    meals = sum(MEAL_PER_DAY.values()) * days
    if family:
        meals *= 1.35
    transit = CITY_TRANSIT_PER_DAY * days + intercity_price
    total = tickets_total + meals + transit
    return {
        "tickets": round(tickets_total),
        "meals": round(meals),
        "transit": round(transit),
        "total": round(total),
        "per_day": round(total / days, 1),
    }
