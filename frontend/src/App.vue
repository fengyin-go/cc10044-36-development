<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">湖仓一体任务编排与数据治理平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向数据湖和数据仓库的ETL任务编排、分区管理、数据血缘和质量治理的工程平台</span>
        <span class="head-user">当前值班：数据工程组</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
const navItems = [{ label: "运营概览", path: "/" }, { label: "上线审查", path: "/release-review" }, { label: "ETL流水线", path: "/etl_pipeline" }, { label: "分区管理", path: "/partition_manager" }, { label: "数据质量规则", path: "/data_quality_rule" }, { label: "Schema变更管理", path: "/schema_change" }, { label: "数据血缘", path: "/lineage_graph" }, { label: "补数任务", path: "/backfill_task" }, { label: "表归档管理", path: "/table_archive" }, { label: "聚合表构建器", path: "/agg_builder" }, { label: "流水线监控", path: "/pipeline_monitor" }, { label: "冷数据恢复", path: "/cold_restore" }, { label: "维度表生成器", path: "/dimension_builder" }, { label: "数据保留策略", path: "/data_retention" }, { label: "转换方案", path: "/transform_plan" }, { label: "数据迁移任务", path: "/data_migration" }, { label: "增量合并引擎", path: "/delta_merge" }, { label: "快照生成器", path: "/snapshot_creator" }, { label: "湖仓审计", path: "/data_lake_audit" }, { label: "SLA策略", path: "/sla_policy" }, { label: "清理作业", path: "/cleanup_job" }, { label: "目录同步", path: "/catalog_sync" }]
</script>
