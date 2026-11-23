"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。"""
from __future__ import annotations

from app.routers import release, resource

# 固定前缀的专用路由必须先注册，否则会被资源路由 /api/{module}/{entry_id} 抢先匹配。
ROUTERS = [release, resource]
