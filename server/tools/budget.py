MEAL_PER_DAY = {"早餐": 15, "午餐": 45, "晚餐": 60}
CITY_TRANSIT_PER_DAY = 35


def budget(days, tickets_total, intercity_price=0, family=False):
    """budget 工具：预算核算。餐饮亲子模式上浮（加儿童餐与零食）。

    days<=0 时 per_day 记 0.0 而非除零（03M P0-05：空候选请求曾在此崩溃）——
    0 天的「日均」本无定义，防御性兜底；空候选的语义降级在 planner 提前返回处理。
    """
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
        "per_day": round(total / days, 1) if days else 0.0,
    }
