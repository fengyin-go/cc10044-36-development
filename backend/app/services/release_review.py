"""上线审查领域服务：按转换步骤读入样本、核验转换输出，并生成上线阶段清单。

数据链路位置：发布治理层。转换方案负责描述步骤依赖，本服务负责回答两个问题：
1. 某一步骤的候选版本，用真实样本跑出来的输出是否可信；
2. ETL 部署下一次处理某个分支时，应该采用哪个版本、写入哪张输出表。

样本核验记录会固化核验当时的输入、输出和转换版本，后续样本或方案变化不会
回写历史记录。没有样本的步骤始终保持“样本缺失”，不会被标成已核验。
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from app.store import store

BRANCH_ORDER = ["订单", "访问"]
BRANCH_PIPELINES: dict[str, list[int]] = {"订单": [1], "访问": [6]}

# 样本模板只用于页面预填，不会自动成为核验记录。
_ORDER_CLEAN_INPUT = [
    {"order_id": "O1001", "amount": 120.5, "dt": "2026-11-21", "customer_id": "C1", "status": "PAID"},
    {"order_id": "O1002", "amount": 80.0, "dt": "2026-11-21", "customer_id": "C2", "status": "PAID"},
    {"order_id": "O1001", "amount": 120.5, "dt": "2026-11-21", "customer_id": "C1", "status": "PAID"},
    {"order_id": "O1003", "amount": 50.0, "dt": "2026-11-22", "customer_id": "C3", "status": "PAID"},
]
_ORDER_CLEAN_OUTPUT = [
    {"order_id": "O1001", "amount": 120.5, "dt": "2026-11-21", "customer_id": "C1", "status": "PAID"},
    {"order_id": "O1002", "amount": 80.0, "dt": "2026-11-21", "customer_id": "C2", "status": "PAID"},
    {"order_id": "O1003", "amount": 50.0, "dt": "2026-11-22", "customer_id": "C3", "status": "PAID"},
]
_ORDER_AGG_OUTPUT = [
    {"dt": "2026-11-21", "amount": 200.5, "order_count": 2},
    {"dt": "2026-11-22", "amount": 50.0, "order_count": 1},
]
_ACCESS_CLEAN_INPUT = [
    {"request_id": "A1", "url": "/home", "status_code": 200, "dt": "2026-11-21", "duration_ms": 120},
    {"request_id": "A2", "url": "/cart", "status_code": 200, "dt": "2026-11-21", "duration_ms": 80},
    {"request_id": "A1", "url": "/home", "status_code": 200, "dt": "2026-11-21", "duration_ms": 120},
    {"request_id": "A3", "url": "/pay", "status_code": 500, "dt": "2026-11-22", "duration_ms": 900},
]
_ACCESS_CLEAN_OUTPUT = [
    {"request_id": "A1", "url": "/home", "status_code": 200, "dt": "2026-11-21", "duration_ms": 120},
    {"request_id": "A2", "url": "/cart", "status_code": 200, "dt": "2026-11-21", "duration_ms": 80},
    {"request_id": "A3", "url": "/pay", "status_code": 500, "dt": "2026-11-22", "duration_ms": 900},
]
_ACCESS_AGG_OUTPUT = [
    {"dt": "2026-11-21", "duration_ms": 200, "request_count": 2},
    {"dt": "2026-11-22", "duration_ms": 900, "request_count": 1},
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _version_key(version: str) -> tuple[int, str]:
    digits = "".join(ch for ch in str(version) if ch.isdigit())
    return (int(digits or 0), str(version))


def _as_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ReleaseReviewService:
    """独立于通用资源表的上线治理状态，保持历史审查与取数记录可追溯。"""

    def __init__(self) -> None:
        self._samples: list[dict[str, Any]] = []
        self._reviews: list[dict[str, Any]] = []
        self._orders: list[dict[str, Any]] = []
        self._applications: list[dict[str, Any]] = []
        self._fetch_records: list[dict[str, Any]] = []
        self._fetch_runs: list[dict[str, Any]] = []
        self._counters: dict[str, int] = {
            "sample": 0, "review": 0, "order": 0, "application": 0,
            "fetch_record": 0, "fetch_run": 0,
        }
        self._seed()

    # ------------------------------------------------------------------ seed
    def _seed(self) -> None:
        self._orders.append({
            "id": self._next("order"),
            "order_no": "REL-20261121-01",
            "title": "订单与访问双分支上线单",
            "branches": ["订单", "访问"],
            "targets": {"订单": "v2", "访问": "v2"},
            "status": "草稿",
            "created_at": "2026-11-21T00:00:00Z",
            "updated_at": "2026-11-21T00:00:00Z",
            "last_application_no": "",
            "submissions": [],
            "remarks": "同一张上线单替换订单和访问两个分支；样本缺失的分支保持现行版本。",
        })

        # 订单分支：清洗与聚合的 v2 样本都已核验通过。
        clean = self.ingest_sample({
            "plan_id": 4, "batch": "2026-11-21",
            "input": _ORDER_CLEAN_INPUT, "output": _ORDER_CLEAN_OUTPUT,
        })["sample"]
        self.verify_sample(clean["id"], verified_at="2026-11-21T00:30:00Z")
        agg = self.ingest_sample({
            "plan_id": 6, "batch": "2026-11-21",
            "input": _ORDER_CLEAN_OUTPUT, "output": _ORDER_AGG_OUTPUT,
        })["sample"]
        self.verify_sample(agg["id"], verified_at="2026-11-21T00:40:00Z")

        # 访问分支：聚合 v2 样本已核验，清洗 v2 的日志样本还没到。
        access_agg = self.ingest_sample({
            "plan_id": 10, "batch": "2026-11-20",
            "input": _ACCESS_CLEAN_OUTPUT, "output": _ACCESS_AGG_OUTPUT,
        })["sample"]
        self.verify_sample(access_agg["id"], verified_at="2026-11-20T23:30:00Z")

    def _next(self, kind: str) -> int:
        self._counters[kind] += 1
        return self._counters[kind]

    # --------------------------------------------------------------- queries
    def plans(self, branch: str | None = None) -> list[dict[str, Any]]:
        rows = [row for row in store.rows("transform_plan") if row.get("分支")]
        if branch:
            rows = [row for row in rows if row.get("分支") == branch]
        rows.sort(key=lambda row: (
            BRANCH_ORDER.index(row["分支"]) if row["分支"] in BRANCH_ORDER else 99,
            int(row.get("阶段序号") or 0), _version_key(row.get("版本", "")),
        ))
        return [self._enrich_plan(row) for row in rows]

    def _enrich_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        state = self._sample_state(plan)
        return {
            "plan_id": plan.get("id"),
            "plan_name": plan.get("方案名称"),
            "branch": plan.get("分支"),
            "step_key": plan.get("步骤键"),
            "step_name": plan.get("步骤名称"),
            "seq": int(plan.get("阶段序号") or 0),
            "version": plan.get("版本"),
            "status": plan.get("status"),
            "online_status": plan.get("上线状态"),
            "input_table": plan.get("输入表"),
            "output_table": plan.get("输出表"),
            "production_table": plan.get("生产表"),
            "sample_status": state["sample_status"],
            "verified": state["verified"],
            "sample_id": state["sample_id"],
            "review_id": state["review_id"],
        }

    def list_samples(self, *, branch: str | None = None, version: str | None = None,
                     step_key: str | None = None) -> list[dict[str, Any]]:
        rows = copy.deepcopy(self._samples)
        if branch:
            rows = [row for row in rows if row["branch"] == branch]
        if version:
            rows = [row for row in rows if row["version"] == version]
        if step_key:
            rows = [row for row in rows if row["step_key"] == step_key]
        return sorted(rows, key=lambda row: row["id"], reverse=True)

    def list_reviews(self, *, branch: str | None = None, version: str | None = None,
                     step_key: str | None = None) -> list[dict[str, Any]]:
        rows = [self._review_view(row) for row in self._reviews]
        if branch:
            rows = [row for row in rows if row["branch"] == branch]
        if version:
            rows = [row for row in rows if row["plan_version"] == version]
        if step_key:
            rows = [row for row in rows if row["step_key"] == step_key]
        return sorted(rows, key=lambda row: row["id"], reverse=True)

    def samples_for_plan(self, plan_id: int) -> list[dict[str, Any]]:
        return [copy.deepcopy(row) for row in self._samples if row["plan_id"] == plan_id]

    def sample_template(self, plan_id: int) -> dict[str, Any]:
        plan = self._plan(plan_id)
        if plan is None:
            return {"ok": False, "message": "转换方案不存在"}
        step_key = plan.get("步骤键")
        kind = (plan.get("校验") or {}).get("类型")
        if step_key == "order_clean":
            return {"ok": True, "plan_id": plan_id, "batch": "2026-11-21",
                    "input": copy.deepcopy(_ORDER_CLEAN_INPUT), "output": copy.deepcopy(_ORDER_CLEAN_OUTPUT)}
        if step_key == "order_agg":
            return {"ok": True, "plan_id": plan_id, "batch": "2026-11-21",
                    "input": copy.deepcopy(_ORDER_CLEAN_OUTPUT), "output": copy.deepcopy(_ORDER_AGG_OUTPUT)}
        if step_key == "access_clean":
            return {"ok": True, "plan_id": plan_id, "batch": "2026-11-21",
                    "input": copy.deepcopy(_ACCESS_CLEAN_INPUT), "output": copy.deepcopy(_ACCESS_CLEAN_OUTPUT)}
        if step_key == "access_agg":
            return {"ok": True, "plan_id": plan_id, "batch": "2026-11-21",
                    "input": copy.deepcopy(_ACCESS_CLEAN_OUTPUT), "output": copy.deepcopy(_ACCESS_AGG_OUTPUT)}
        rule = plan.get("校验") or {}
        return {
            "ok": True, "plan_id": plan_id, "batch": "2026-11-21",
            "input": [{"id": "sample-1"}],
            "output": [{"id": "sample-1"}],
            "message": f"该步骤校验类型为 {rule.get('类型', '通用')}，请按实际表结构替换样本。",
            "kind": kind,
        }

    # --------------------------------------------------------------- samples
    def ingest_sample(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan, error = self._resolve_plan(payload)
        if error:
            return {"ok": False, "message": error}
        assert plan is not None
        input_rows = payload.get("input", payload.get("输入", []))
        output_rows = payload.get("output", payload.get("输出", []))
        if not isinstance(input_rows, list) or not all(isinstance(row, dict) for row in input_rows):
            return {"ok": False, "message": "样本输入必须是对象数组"}
        if not isinstance(output_rows, list) or not all(isinstance(row, dict) for row in output_rows):
            return {"ok": False, "message": "样本输出必须是对象数组"}
        if not input_rows:
            return {"ok": False, "message": "样本输入不能为空，空白样本不能参与核验"}
        if not output_rows:
            return {"ok": False, "message": "样本输出不能为空，空白样本不能参与核验"}

        sample = {
            "id": self._next("sample"),
            "plan_id": int(plan["id"]),
            "plan_name": plan.get("方案名称"),
            "branch": plan.get("分支"),
            "step_key": plan.get("步骤键"),
            "step_name": plan.get("步骤名称"),
            "version": plan.get("版本"),
            "batch": str(payload.get("batch") or payload.get("样本批次") or "未标注"),
            "status": "待核验",
            "input": copy.deepcopy(input_rows),
            "output": copy.deepcopy(output_rows),
            "input_rows": len(input_rows),
            "output_rows": len(output_rows),
            "created_at": _now(),
            "verified_at": "",
            "review_id": None,
        }
        self._samples.append(sample)
        return {"ok": True, "sample": copy.deepcopy(sample), "message": "样本已录入，等待核验"}

    def verify_sample(self, sample_id: int, *, verified_at: str | None = None) -> dict[str, Any]:
        sample = next((row for row in self._samples if row["id"] == sample_id), None)
        if sample is None:
            return {"ok": False, "message": "样本不存在"}
        plan = self._plan(sample["plan_id"])
        if plan is None:
            return {"ok": False, "message": "样本关联的转换方案不存在"}
        if sample["version"] != plan.get("版本"):
            return {"ok": False, "message": "样本版本与转换方案版本不一致，不能核验"}

        rules = plan.get("校验") or {}
        kind = rules.get("类型")
        if kind == "clean":
            passed, checks = self._validate_clean(sample["input"], sample["output"], rules)
        elif kind == "agg":
            passed, checks = self._validate_agg(sample["input"], sample["output"], rules)
        else:
            passed, checks = self._validate_generic(sample["input"], sample["output"])
        issues = [check["detail"] for check in checks if not check["passed"]]

        review = {
            "id": self._next("review"),
            "sample_id": sample["id"],
            "plan_id": sample["plan_id"],
            "plan_name": sample["plan_name"],
            "branch": sample["branch"],
            "step_key": sample["step_key"],
            "step_name": sample["step_name"],
            "plan_version": sample["version"],
            "transform_version": f"{sample['plan_name']}@{sample['version']}",
            "sample_batch": sample["batch"],
            "status": "已核验" if passed else "未通过",
            "passed": passed,
            "checks": checks,
            "issues": issues,
            "input_snapshot": copy.deepcopy(sample["input"]),
            "output_snapshot": copy.deepcopy(sample["output"]),
            "input_rows": sample["input_rows"],
            "output_rows": sample["output_rows"],
            "verified_at": verified_at or _now(),
        }
        self._reviews.append(review)
        sample["status"] = "已核验" if passed else "未通过"
        sample["verified_at"] = review["verified_at"]
        sample["review_id"] = review["id"]
        return {
            "ok": True,
            "passed": passed,
            "review": self._review_view(review),
            "message": (
                f"{sample['step_name']} {sample['version']} 样本核验通过"
                if passed else
                f"{sample['step_name']} {sample['version']} 样本核验未通过：{'；'.join(issues)}"
            ),
        }

    def verify_and_ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        ingested = self.ingest_sample(payload)
        if not ingested.get("ok"):
            return ingested
        review = self.verify_sample(ingested["sample"]["id"])
        if not review.get("ok"):
            return review
        review["sample"] = ingested["sample"]
        return review

    # -------------------------------------------------------------- checklist
    def build_checklist(self, order_id: int) -> dict[str, Any]:
        order = self._order(order_id)
        if order is None:
            return {"ok": False, "message": "上线单不存在"}
        return self._checklist_for_order(order)

    def _checklist_for_order(self, order: dict[str, Any]) -> dict[str, Any]:
        branch_items: list[dict[str, Any]] = []
        for branch in order.get("branches", []):
            target_version = order["targets"].get(branch, "")
            current_version = self._live_version(branch)
            target_plans = self._plans_for(branch, target_version)
            current_plans = self._plans_for(branch, current_version)
            current_by_step = {plan.get("步骤键"): plan for plan in current_plans}

            step_items: list[dict[str, Any]] = []
            target_states: dict[str, dict[str, Any]] = {}
            for plan in sorted(target_plans, key=lambda row: int(row.get("阶段序号") or 0)):
                state = self._sample_state(plan)
                target_states[plan.get("步骤键", "")] = state
                current_plan = current_by_step.get(plan.get("步骤键"))
                gate_passed: bool | None = None
                gate_reason = ""
                kind = (plan.get("校验") or {}).get("类型")
                if kind == "agg":
                    clean_state = target_states.get(self._clean_step_key(branch, target_version))
                    gate_passed = bool(clean_state and clean_state["verified"])
                    gate_reason = (
                        "同版清洗核验通过" if gate_passed
                        else "同版清洗样本缺失或未通过，聚合不能单独上线"
                    )
                if not state["verified"]:
                    decision = state["sample_status"] + "，保持现行版本"
                elif gate_passed is False:
                    decision = "聚合受同版清洗门禁限制，保持现行版本"
                else:
                    decision = "核验通过，可随分支上线"
                step_items.append({
                    "step_key": plan.get("步骤键"),
                    "step_name": plan.get("步骤名称"),
                    "seq": int(plan.get("阶段序号") or 0),
                    "current_plan_id": current_plan.get("id") if current_plan else None,
                    "current_version": current_version,
                    "current_output_table": current_plan.get("输出表") if current_plan else "",
                    "candidate_plan_id": plan.get("id"),
                    "candidate_version": target_version,
                    "candidate_output_table": plan.get("输出表"),
                    "sample_id": state["sample_id"],
                    "sample_batch": state["sample_batch"],
                    "sample_status": state["sample_status"],
                    "review_id": state["review_id"],
                    "verified": state["verified"],
                    "gate_passed": gate_passed,
                    "gate_reason": gate_reason,
                    "decision": decision,
                })

            branch_ready = bool(target_plans) and all(
                item["verified"] and item["gate_passed"] is not False for item in step_items
            )
            if current_version == target_version:
                branch_ready = True
                branch_reason = f"分支已处于目标版本 {target_version}"
            elif branch_ready:
                branch_reason = f"{target_version} 全部步骤核验通过，切换到新版本"
            else:
                blocked = [
                    f"{item['step_name']}({item['sample_status']})"
                    for item in step_items
                    if not item["verified"]
                ]
                if not blocked:
                    blocked = [
                        f"{item['step_name']}({item['gate_reason']})"
                        for item in step_items
                        if item["gate_passed"] is False
                    ]
                branch_reason = "保持已上线版本 " + current_version + "：" + "、".join(blocked)
            adopted_version = target_version if branch_ready else current_version
            adopted_plans = self._plans_for(branch, adopted_version)
            for item in step_items:
                if branch_ready and item["candidate_version"] == target_version:
                    item["adopted_plan_id"] = item["candidate_plan_id"]
                    item["adopted_version"] = target_version
                    item["output_table"] = item["candidate_output_table"]
                else:
                    item["adopted_plan_id"] = item["current_plan_id"]
                    item["adopted_version"] = current_version
                    item["output_table"] = item["current_output_table"]
            final_plan = max(
                adopted_plans,
                key=lambda row: int(row.get("阶段序号") or 0),
                default=None,
            )
            branch_items.append({
                "branch": branch,
                "current_version": current_version,
                "target_version": target_version,
                "adopted_version": adopted_version,
                "ready": branch_ready,
                "reason": branch_reason,
                "production_table": (final_plan or {}).get("生产表", ""),
                "output_table": (final_plan or {}).get("输出表", ""),
                "plan_id": (final_plan or {}).get("id"),
                "plan_name": (final_plan or {}).get("方案名称", ""),
                "steps": step_items,
            })

        production_outputs = [
            {
                "branch": item["branch"],
                "production_table": item["production_table"],
                "adopted_version": item["adopted_version"],
                "output_table": item["output_table"],
                "plan_id": item["plan_id"],
                "plan_name": item["plan_name"],
            }
            for item in branch_items
        ]
        return {
            "order_id": order["id"],
            "order_no": order["order_no"],
            "title": order["title"],
            "generated_at": _now(),
            "branches": branch_items,
            "production_outputs": production_outputs,
        }

    # ---------------------------------------------------------------- release
    def submit_order(self, order_id: int) -> dict[str, Any]:
        order = self._order(order_id)
        if order is None:
            return {"ok": False, "message": "上线单不存在"}
        checklist = self._checklist_for_order(order)
        previous_versions = {item["branch"]: item["current_version"] for item in checklist["branches"]}
        adopted_versions = {item["branch"]: item["adopted_version"] for item in checklist["branches"]}

        # 先固化清单再推进上线状态，清单保留提交当时的分支版本判断。
        for item in checklist["branches"]:
            if item["adopted_version"] != item["current_version"]:
                self._apply_branch_version(item["branch"], item["adopted_version"])

        revision = len(order["submissions"]) + 1
        application_no = f"{order['order_no']}-R{revision}"
        application = {
            "id": self._next("application"),
            "application_no": application_no,
            "order_id": order["id"],
            "revision": revision,
            "created_at": _now(),
            "deployed_at": "",
            "previous_versions": previous_versions,
            "adopted_versions": adopted_versions,
            "checklist": checklist,
            "pipeline_bindings": [],
        }
        self._applications.append(application)
        order["submissions"].append({
            "revision": revision,
            "application_no": application_no,
            "submitted_at": application["created_at"],
            "previous_versions": previous_versions,
            "adopted_versions": adopted_versions,
        })
        order["last_application_no"] = application_no
        order["updated_at"] = application["created_at"]
        all_target = all(
            item["adopted_version"] == item["target_version"] for item in checklist["branches"]
        )
        any_target = any(
            item["adopted_version"] == item["target_version"] for item in checklist["branches"]
        )
        order["status"] = "已全部上线" if all_target else ("部分上线" if any_target else "已提交")
        summary = "；".join(
            f"{item['branch']}采用 {item['adopted_version']}（{item['output_table']}）"
            for item in checklist["branches"]
        )
        return {
            "ok": True,
            "order_id": order["id"],
            "order_no": order["order_no"],
            "revision": revision,
            "application_no": application_no,
            "status": order["status"],
            "summary": summary,
            "previous_versions": previous_versions,
            "adopted_versions": adopted_versions,
            "checklist": checklist,
            "message": f"上线单 {order['order_no']} 第 {revision} 次提交：{summary}",
        }

    def deploy_order(self, order_id: int) -> dict[str, Any]:
        order = self._order(order_id)
        if order is None:
            return {"ok": False, "message": "上线单不存在"}
        if not order["submissions"]:
            submitted = self.submit_order(order_id)
            if not submitted.get("ok"):
                return submitted
        application = self._latest_application(order_id)
        if application is None:
            return {"ok": False, "message": "上线单尚未形成上线阶段清单"}
        checklist = application["checklist"]
        bindings: list[dict[str, Any]] = []
        for item in checklist["branches"]:
            for pipeline_id in BRANCH_PIPELINES.get(item["branch"], []):
                pipeline = store.find("etl_pipeline", pipeline_id)
                if pipeline is None:
                    continue
                pipeline["转换方案ID"] = str(item["plan_id"] or "")
                pipeline["采用版本"] = item["adopted_version"]
                pipeline["输出数据表"] = item["output_table"]
                pipeline["上线单号"] = order["order_no"]
                bindings.append({
                    "pipeline_id": pipeline_id,
                    "pipeline_name": pipeline.get("流水线名称"),
                    "branch": item["branch"],
                    "adopted_version": item["adopted_version"],
                    "plan_id": item["plan_id"],
                    "output_table": item["output_table"],
                })
        application["deployed_at"] = _now()
        application["pipeline_bindings"] = bindings
        return {
            "ok": True,
            "order_id": order_id,
            "application_no": application["application_no"],
            "checklist": checklist,
            "pipeline_bindings": bindings,
            "message": f"ETL 部署已接收上线请求，按清单为 {len(bindings)} 个流水线阶段选择版本",
        }

    def order_detail(self, order_id: int) -> dict[str, Any] | None:
        order = self._order(order_id)
        if order is None:
            return None
        application = self._latest_application(order_id)
        return {
            **copy.deepcopy(order),
            "checklist": application["checklist"] if application else self._checklist_for_order(order),
            "latest_application": copy.deepcopy(application) if application else None,
        }

    def orders(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(order) for order in self._orders]

    def live_versions(self) -> dict[str, Any]:
        result = {}
        for branch in BRANCH_ORDER:
            version = self._live_version(branch)
            plans = self._plans_for(branch, version)
            final_plan = max(plans, key=lambda row: int(row.get("阶段序号") or 0), default=None)
            result[branch] = {
                "version": version,
                "plan_id": (final_plan or {}).get("id"),
                "output_table": (final_plan or {}).get("输出表", ""),
                "production_table": (final_plan or {}).get("生产表", ""),
            }
        return result

    # ------------------------------------------------------------------ fetch
    def run_fetch(self, payload: dict[str, Any]) -> dict[str, Any]:
        tables = payload.get("tables") or payload.get("数据表") or []
        if isinstance(tables, str):
            tables = [item.strip() for item in tables.split(",") if item.strip()]
        if not tables:
            tables = ["dws_order_daily", "dws_access_daily"]
        batch_date = str(payload.get("batch_date") or payload.get("批次") or "2026-11-21")
        application = self._latest_application()
        results: list[dict[str, Any]] = []
        new_records: list[dict[str, Any]] = []
        for requested_table in tables:
            requested_table = str(requested_table).strip()
            branch = self._branch_for_table(requested_table)
            if branch is None:
                results.append({
                    "requested_table": requested_table,
                    "production_table": requested_table,
                    "branch": "",
                    "adopted_version": "",
                    "output_table": "",
                    "executed": False,
                    "skipped": True,
                    "status": "未知数据表",
                    "message": f"{requested_table} 没有登记生产表或输出表，未发起取数",
                })
                continue
            decision = self._table_decision(branch, application)
            production_table = decision["production_table"]
            existing = self._fetch_record(
                production_table, batch_date, decision["adopted_version"])
            if existing is not None:
                cross_version = existing["plan_version"] != decision["adopted_version"]
                results.append({
                    "requested_table": requested_table,
                    "production_table": production_table,
                    "branch": branch,
                    "adopted_version": decision["adopted_version"],
                    "plan_id": decision["plan_id"],
                    "plan_name": decision["plan_name"],
                    "output_table": decision["output_table"],
                    "executed": False,
                    "skipped": True,
                    "status": "已处理，跳过",
                    "previous_version": existing["plan_version"],
                    "previous_output_table": existing["output_table"],
                    "previous_executed_at": existing["executed_at"],
                    "message": (
                        f"批次 {batch_date} 已由 {existing['plan_version']} 写入 "
                        f"{existing['output_table']}，同批次不重复执行"
                        + (
                            f"；本次清单已切到 {decision['adopted_version']}，"
                            "新版本从下一批次开始生效"
                            if cross_version else ""
                        )
                    ),
                })
                continue

            record = {
                "id": self._next("fetch_record"),
                "run_id": 0,
                "production_table": production_table,
                "branch": branch,
                "batch_date": batch_date,
                "plan_id": decision["plan_id"],
                "plan_name": decision["plan_name"],
                "plan_version": decision["adopted_version"],
                "output_table": decision["output_table"],
                "application_no": decision["application_no"],
                "row_count": self._row_count_for(decision["plan_id"]),
                "status": "已执行",
                "executed_at": _now(),
            }
            self._fetch_records.append(record)
            new_records.append(record)
            results.append({
                "requested_table": requested_table,
                "production_table": production_table,
                "branch": branch,
                "adopted_version": decision["adopted_version"],
                "plan_id": decision["plan_id"],
                "plan_name": decision["plan_name"],
                "output_table": decision["output_table"],
                "executed": True,
                "skipped": False,
                "status": "已执行",
                "row_count": record["row_count"],
                "reason": decision["reason"],
                "message": (
                    f"{branch}分支按 {decision['adopted_version']} 处理，输出到 "
                    f"{decision['output_table']}"
                ),
            })

        run = {
            "id": self._next("fetch_run"),
            "batch_date": batch_date,
            "application_no": application["application_no"] if application else "",
            "requested_at": _now(),
            "requested_tables": list(tables),
            "executed": sum(1 for item in results if item["executed"]),
            "skipped": sum(1 for item in results if item.get("skipped")),
        }
        for record in new_records:
            record["run_id"] = run["id"]
        self._fetch_runs.append(run)
        return {
            "ok": True,
            "batch_date": batch_date,
            "application_no": run["application_no"],
            "tables": results,
            "fetch_run": run,
            "message": (
                f"取数完成：执行 {run['executed']} 张表，跳过 {run['skipped']} 张表"
            ),
        }

    def fetch_history(self) -> dict[str, Any]:
        return {
            "runs": copy.deepcopy(list(reversed(self._fetch_runs))),
            "records": copy.deepcopy(list(reversed(self._fetch_records))),
        }

    def usage(self, tables: list[str] | None = None) -> dict[str, Any]:
        records = copy.deepcopy(self._fetch_records)
        if tables:
            wanted = {self._branch_for_table(table) for table in tables}
            records = [row for row in records if row["branch"] in wanted]
        records.sort(key=lambda row: (row["executed_at"], row["id"]))
        branches: list[dict[str, Any]] = []
        for branch in BRANCH_ORDER:
            branch_records = [row for row in records if row["branch"] == branch]
            if tables and not branch_records:
                # 没取过数时也展示当前版本，便于核对“旧版/新版”的使用边界。
                if not any(self._branch_for_table(table) == branch for table in tables):
                    continue
            versions: dict[str, list[dict[str, Any]]] = {}
            for record in branch_records:
                versions.setdefault(record["plan_version"], []).append(record)
            branches.append({
                "branch": branch,
                "current_version": self._live_version(branch),
                "versions": [
                    {
                        "version": version,
                        "executions": len(rows),
                        "plan_ids": sorted({row["plan_id"] for row in rows if row["plan_id"]}),
                        "output_tables": sorted({row["output_table"] for row in rows if row["output_table"]}),
                        "batches": sorted({row["batch_date"] for row in rows}),
                        "records": rows,
                    }
                    for version, rows in sorted(versions.items(), key=lambda pair: _version_key(pair[0]))
                ],
            })
        return {
            "records": records,
            "by_branch": branches,
            "total_executions": len(records),
        }

    def overview(self) -> dict[str, Any]:
        pending: list[dict[str, Any]] = []
        for branch in BRANCH_ORDER:
            target = "v2"
            live = self._live_version(branch)
            for plan in self._plans_for(branch, target):
                state = self._sample_state(plan)
                if target != live and not state["verified"]:
                    pending.append({
                        "branch": branch,
                        "step_key": plan.get("步骤键"),
                        "step_name": plan.get("步骤名称"),
                        "version": target,
                        "sample_status": state["sample_status"],
                    })
        return {
            "orders": [
                {
                    "id": order["id"],
                    "order_no": order["order_no"],
                    "title": order["title"],
                    "status": order["status"],
                    "targets": copy.deepcopy(order["targets"]),
                    "last_application_no": order["last_application_no"],
                    "submissions": len(order["submissions"]),
                }
                for order in self._orders
            ],
            "live": self.live_versions(),
            "pending_samples": pending,
            "reviews": len(self._reviews),
            "fetch_executions": len(self._fetch_records),
        }

    # --------------------------------------------------------------- helpers
    def _order(self, order_id: int) -> dict[str, Any] | None:
        return next((row for row in self._orders if row["id"] == order_id), None)

    def _latest_application(self, order_id: int | None = None) -> dict[str, Any] | None:
        candidates = [
            row for row in self._applications
            if order_id is None or row["order_id"] == order_id
        ]
        return candidates[-1] if candidates else None

    def _plan(self, plan_id: int | str | None) -> dict[str, Any] | None:
        try:
            wanted = int(plan_id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        for row in store.rows("transform_plan"):
            if int(row.get("id", 0)) == wanted:
                return row
        return None

    def _resolve_plan(self, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if payload.get("plan_id") is not None:
            plan = self._plan(payload.get("plan_id"))
            if plan is None:
                return None, "转换方案不存在"
            if payload.get("branch") and payload["branch"] != plan.get("分支"):
                return None, "样本分支与转换方案不一致"
            if payload.get("step_key") and payload["step_key"] != plan.get("步骤键"):
                return None, "样本步骤与转换方案不一致"
            if payload.get("version") and payload["version"] != plan.get("版本"):
                return None, "样本版本与转换方案不一致"
            return plan, ""
        branch = payload.get("branch") or payload.get("分支")
        step_key = payload.get("step_key") or payload.get("步骤键")
        version = payload.get("version") or payload.get("版本")
        if not all([branch, step_key, version]):
            return None, "请提供 plan_id，或同时提供 branch、step_key、version"
        for row in store.rows("transform_plan"):
            if (row.get("分支") == branch and row.get("步骤键") == step_key
                    and row.get("版本") == version):
                return row, ""
        return None, f"未找到 {branch}/{step_key}/{version} 对应的转换方案"

    def _plans_for(self, branch: str, version: str) -> list[dict[str, Any]]:
        rows = [
            row for row in store.rows("transform_plan")
            if row.get("分支") == branch and row.get("版本") == version
        ]
        return sorted(rows, key=lambda row: int(row.get("阶段序号") or 0))

    def _live_version(self, branch: str) -> str:
        live = [
            row for row in store.rows("transform_plan")
            if row.get("分支") == branch and row.get("上线状态") == "已上线"
        ]
        if not live:
            all_versions = [
                row.get("版本") for row in store.rows("transform_plan")
                if row.get("分支") == branch and row.get("版本")
            ]
            return sorted(set(all_versions), key=_version_key)[0] if all_versions else "v1"
        versions = {row.get("版本") for row in live if row.get("版本")}
        return sorted(versions, key=_version_key)[-1]

    def _apply_branch_version(self, branch: str, version: str) -> None:
        for row in store.rows("transform_plan"):
            if row.get("分支") != branch:
                continue
            if row.get("版本") == version:
                row["上线状态"] = "已上线"
                row["status"] = "已发布"
                row["pending"] = False
                row["abnormal"] = False
            elif row.get("上线状态") == "已上线":
                row["上线状态"] = "已下线"
                row["pending"] = False

    def _clean_step_key(self, branch: str, version: str) -> str:
        for plan in self._plans_for(branch, version):
            if (plan.get("校验") or {}).get("类型") == "clean":
                return plan.get("步骤键", "")
        return ""

    def _sample_state(self, plan: dict[str, Any]) -> dict[str, Any]:
        samples = [row for row in self._samples if row["plan_id"] == plan.get("id")]
        if not samples:
            return {
                "sample_status": "样本缺失", "verified": False, "sample_id": None,
                "sample_batch": "", "review_id": None,
            }
        latest = max(samples, key=lambda row: row["id"])
        review = next(
            (row for row in self._reviews if row["sample_id"] == latest["id"]),
            None,
        )
        if review is None:
            status = "待核验"
            verified = False
        elif review["passed"]:
            status = "已核验"
            verified = True
        else:
            status = "核验未通过"
            verified = False
        return {
            "sample_status": status,
            "verified": verified,
            "sample_id": latest["id"],
            "sample_batch": latest["batch"],
            "review_id": review["id"] if review else None,
        }

    def _review_view(self, review: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(review)

    def _validate_clean(self, input_rows: list[dict[str, Any]],
                        output_rows: list[dict[str, Any]],
                        rules: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
        required = rules.get("必填") or []
        primary_key = rules.get("主键") or "id"
        checks: list[dict[str, Any]] = []
        checks.append({
            "check": "输出非空", "passed": bool(output_rows),
            "detail": f"输出 {len(output_rows)} 行",
        })
        missing: list[dict[str, Any]] = []
        nulls: list[dict[str, Any]] = []
        for index, row in enumerate(output_rows):
            absent = [field for field in required if field not in row or row.get(field) in (None, "")]
            if absent:
                missing.append({"row": index, "fields": absent})
            for field in required:
                if field in row and row.get(field) is None:
                    nulls.append({"row": index, "field": field})
        checks.append({
            "check": "必填字段完整", "passed": not missing,
            "detail": "必填字段齐全" if not missing else f"{len(missing)} 行缺少必填字段：{missing[:3]}",
        })
        keys = [str(row.get(primary_key)) for row in output_rows if row.get(primary_key) not in (None, "")]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        checks.append({
            "check": "主键唯一", "passed": not duplicates,
            "detail": f"主键 {primary_key} 无重复" if not duplicates else f"主键重复：{duplicates[:5]}",
        })
        input_keys = {str(row.get(primary_key)) for row in input_rows}
        unknown = sorted({key for key in keys if key not in input_keys})
        checks.append({
            "check": "输出来源可追溯", "passed": not unknown,
            "detail": "所有输出行都能在输入中找到" if not unknown else f"输出包含输入中不存在的主键：{unknown[:5]}",
        })
        negative = []
        for index, row in enumerate(output_rows):
            for field in ("amount", "duration_ms"):
                if field in row:
                    value = _as_number(row.get(field))
                    if value is not None and value < 0:
                        negative.append({"row": index, "field": field, "value": value})
        checks.append({
            "check": "数值非负", "passed": not negative,
            "detail": "金额/耗时字段非负" if not negative else f"存在负值：{negative[:3]}",
        })
        checks.append({
            "check": "去重不放大", "passed": len(output_rows) <= max(len(input_rows), 1),
            "detail": f"输入 {len(input_rows)} 行，输出 {len(output_rows)} 行",
        })
        passed = all(check["passed"] for check in checks)
        return passed, checks

    def _validate_agg(self, input_rows: list[dict[str, Any]],
                      output_rows: list[dict[str, Any]],
                      rules: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
        dimensions = rules.get("维度") or ["dt"]
        metric = rules.get("指标") or "amount"
        checks: list[dict[str, Any]] = []

        def group_sum(rows: list[dict[str, Any]]) -> dict[tuple[str, ...], float] | None:
            grouped: dict[tuple[str, ...], float] = {}
            for row in rows:
                if any(field not in row for field in dimensions) or metric not in row:
                    return None
                value = _as_number(row.get(metric))
                if value is None:
                    return None
                key = tuple(str(row.get(field)) for field in dimensions)
                grouped[key] = grouped.get(key, 0.0) + value
            return grouped

        source = group_sum(input_rows)
        output = group_sum(output_rows)
        checks.append({
            "check": "维度与指标字段完整", "passed": source is not None and output is not None,
            "detail": f"维度 {dimensions}，指标 {metric}",
        })
        if source is not None and output is not None:
            keys_match = set(source) == set(output)
            diffs = {
                key: round(output.get(key, 0.0) - source.get(key, 0.0), 6)
                for key in set(source) | set(output)
                if abs(output.get(key, 0.0) - source.get(key, 0.0)) > 1e-6
            }
            checks.append({
                "check": "聚合维度覆盖", "passed": keys_match,
                "detail": "输出维度组合与输入一致" if keys_match else f"维度组合不一致：{sorted(set(source) ^ set(output))[:5]}",
            })
            checks.append({
                "check": "聚合值一致", "passed": not diffs,
                "detail": f"{metric} 汇总一致" if not diffs else f"汇总差异：{list(diffs.items())[:5]}",
            })
            checks.append({
                "check": "总量一致", "passed": abs(sum(output.values()) - sum(source.values())) <= 1e-6,
                "detail": f"输入合计 {round(sum(source.values()), 6)}，输出合计 {round(sum(output.values()), 6)}",
            })
        else:
            checks.append({"check": "聚合维度覆盖", "passed": False, "detail": "样本缺少维度或指标字段"})
            checks.append({"check": "聚合值一致", "passed": False, "detail": "无法计算聚合值"})
            checks.append({"check": "总量一致", "passed": False, "detail": "无法计算总量"})
        passed = all(check["passed"] for check in checks)
        return passed, checks

    def _validate_generic(self, input_rows: list[dict[str, Any]],
                          output_rows: list[dict[str, Any]]) -> tuple[bool, list[dict[str, Any]]]:
        checks = [
            {"check": "输入非空", "passed": bool(input_rows), "detail": f"输入 {len(input_rows)} 行"},
            {"check": "输出非空", "passed": bool(output_rows), "detail": f"输出 {len(output_rows)} 行"},
        ]
        return all(check["passed"] for check in checks), checks

    def _branch_for_table(self, table: str) -> str | None:
        for row in store.rows("transform_plan"):
            if row.get("分支") and table in (row.get("生产表"), row.get("输出表")):
                return row["分支"]
        return None

    def _table_decision(self, branch: str, application: dict[str, Any] | None) -> dict[str, Any]:
        if application is not None:
            for item in application["checklist"]["branches"]:
                if item["branch"] == branch:
                    return {
                        "adopted_version": item["adopted_version"],
                        "plan_id": item["plan_id"],
                        "plan_name": item["plan_name"],
                        "output_table": item["output_table"],
                        "production_table": item["production_table"],
                        "application_no": application["application_no"],
                        "reason": item["reason"],
                    }
        version = self._live_version(branch)
        plans = self._plans_for(branch, version)
        final_plan = max(plans, key=lambda row: int(row.get("阶段序号") or 0), default=None)
        return {
            "adopted_version": version,
            "plan_id": (final_plan or {}).get("id"),
            "plan_name": (final_plan or {}).get("方案名称", ""),
            "output_table": (final_plan or {}).get("输出表", ""),
            "production_table": (final_plan or {}).get("生产表", ""),
            "application_no": "",
            "reason": f"没有上线单时继续使用当前已上线阶段 {version}",
        }

    def _fetch_record(self, production_table: str, batch_date: str,
                      version: str | None = None) -> dict[str, Any] | None:
        for row in self._fetch_records:
            if row["production_table"] != production_table or row["batch_date"] != batch_date:
                continue
            if version is None or row["plan_version"] == version:
                return row
        return None

    def _row_count_for(self, plan_id: int | None) -> int:
        plan = self._plan(plan_id)
        if plan is None:
            return 0
        samples = [row for row in self._samples if row["plan_id"] == plan.get("id")]
        if samples:
            return max(samples, key=lambda row: row["id"])["output_rows"]
        return 1000 + int(plan.get("id", 0)) * 137


release_service = ReleaseReviewService()
