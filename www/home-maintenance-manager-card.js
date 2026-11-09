/* Home Maintenance Manager Lovelace card
 * Copy this file to /config/www/home-maintenance-manager-card.js
 */
class HomeMaintenanceManagerCard extends HTMLElement {
  setConfig(config) {
    this.config = {
      title: "Home Maintenance",
      show_equipment: true,
      show_history: true,
      ...config,
    };
    if (this._filter === undefined) this._filter = "all";
    if (this._category === undefined) this._category = "all";
    if (this._equipmentTask === undefined) this._equipmentTask = null;
    if (this._detailTaskKey === undefined) this._detailTaskKey = null;
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  getCardSize() {
    return 5;
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[char]);
  }

  _date(value) {
    if (!value) return "Not scheduled";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Not scheduled";
    return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  _discover() {
    const states = Object.values(this._hass?.states || {});
    const integrationStates = states.filter((state) =>
      state.attributes?.integration_domain === "home_maintenance_manager"
    );
    const taskSensors = integrationStates.filter((state) =>
      state.entity_id.startsWith("sensor.") &&
      state.attributes?.task_id &&
      state.attributes?.enabled !== false
    );
    const buttons = new Map(integrationStates
      .filter((state) => state.entity_id.startsWith("button.") && state.attributes?.task_id)
      .map((state) => [
        `${state.attributes.integration_instance || "default"}:${state.attributes.task_id}`,
        state.entity_id,
      ]));
    const summaryTotals = new Map();
    integrationStates
      .filter((state) => state.entity_id.startsWith("sensor.") && state.attributes?.summary_key)
      .forEach((state) => {
        const key = state.attributes.summary_key;
        const value = Number(state.state);
        if (!Number.isFinite(value)) return;
        summaryTotals.set(key, (summaryTotals.get(key) || 0) + value);
      });
    const equipment = integrationStates.filter((state) =>
      state.entity_id.startsWith("sensor.") && state.attributes?.equipment_id
    );
    return {
      tasks: taskSensors.map((state) => ({
        state,
        button: buttons.get(
          `${state.attributes.integration_instance || "default"}:${state.attributes.task_id}`
        ),
      })).sort((a, b) => {
        const order = { overdue: 0, due_today: 1, due_soon: 2, scheduled: 3, not_scheduled: 4 };
        return (order[a.state.state] ?? 5) - (order[b.state.state] ?? 5) ||
          (a.state.attributes.friendly_name || "").localeCompare(b.state.attributes.friendly_name || "");
      }),
      summaries: summaryTotals,
      equipment,
    };
  }

  _statusLabel(status) {
    return ({
      overdue: "Overdue",
      due_today: "Due today",
      due_soon: "Due soon",
      scheduled: "Scheduled",
      not_scheduled: "Not scheduled",
      disabled: "Disabled",
    })[status] || status;
  }

  _renderTask(item, equipment) {
    const state = item.state;
    const attrs = state.attributes || {};
    const name = (attrs.friendly_name || state.entity_id).replace(/ Status$/, "");
    const status = state.state;
    const key = `${attrs.integration_instance || "default"}:${attrs.task_id}`;
    const action = item.button
      ? `<button class="complete" data-complete-task="${this._escape(attrs.task_id)}" data-instance="${this._escape(attrs.integration_instance || "default")}">Mark complete</button>`
      : '<span class="muted">No completion button</span>';
    const details = this._detailTaskKey === key ? this._renderTaskDetails(item, equipment) : "";
    const detailLabel = this._detailTaskKey === key ? "Hide details" : "Details";
    return `
      <article class="task">
        <div class="task-main">
          <div class="task-name">${this._escape(name)}</div>
          <div class="meta">${this._escape(attrs.category || "General")} · Due: ${this._escape(this._date(attrs.next_due))}</div>
          ${attrs.description ? `<div class="description">${this._escape(attrs.description)}</div>` : ""}
          <button class="details-toggle" data-details="${this._escape(key)}">${detailLabel}</button>
          ${details}
        </div>
        <div class="task-actions">
          <span class="status ${this._escape(status)}">${this._escape(this._statusLabel(status))}</span>
          ${action}
        </div>
      </article>`;
  }

  _renderTaskDetails(item, equipment) {
    const attrs = item.state.attributes || {};
    const linkedEquipment = equipment.filter((entry) =>
      (attrs.equipment_ids || []).includes(entry.attributes.equipment_id) &&
      (entry.attributes.integration_instance || "default") === (attrs.integration_instance || "default")
    );
    const equipmentNames = linkedEquipment.length
      ? linkedEquipment.map((entry) => this._escape(entry.attributes.friendly_name || entry.state)).join(", ")
      : "None linked";
    const history = [...(attrs.completion_history || [])].reverse();
    const historyMarkup = history.length ? history.slice(0, 5).map((record) => `
      <div class="history-item">
        <strong>${this._escape(this._date(record.completed_at))}</strong>
        <span>Previous due: ${this._escape(this._date(record.previous_due))}</span>
        ${record.notes ? `<div class="description">${this._escape(record.notes)}</div>` : ""}
      </div>`).join("") : '<div class="muted">No completion history yet.</div>';
    const interval = attrs.configured_interval_days
      ? `${this._escape(attrs.configured_interval_days)} days`
      : (attrs.schedule_type === "seasonal" ? `Seasonal (${this._escape((attrs.season_keys || []).join(", "))})` : "Not set");
    return `<div class="task-details">
      <div><span>Last completed</span><strong>${this._escape(this._date(attrs.last_completed))}</strong></div>
      <div><span>Next due</span><strong>${this._escape(this._date(attrs.next_due))}</strong></div>
      <div><span>Repeat interval</span><strong>${interval}</strong></div>
      <div><span>Linked equipment</span><strong>${equipmentNames}</strong></div>
      <div class="history-list"><strong>Recent completions</strong>${historyMarkup}</div>
    </div>`;
  }

  render() {
    if (!this._hass || !this.config) return;
    const { tasks, summaries, equipment } = this._discover();
    const count = (key) => summaries.get(key)?.state ?? "—";
    const categories = [...new Set(tasks.map(({ state }) => state.attributes.category || "General"))].sort();
    const filtered = tasks.filter(({ state }) => {
      const category = state.attributes.category || "General";
      if (this._category !== "all" && category !== this._category) return false;
      if (this._equipmentTask && state.attributes.task_id !== this._equipmentTask) return false;
      if (this._filter === "all") return true;
      if (this._filter === "upcoming") return ["due_today", "due_soon"].includes(state.state);
      return state.state === this._filter;
    });
    const categoryMarkup = '<div class="category-filters"><button data-category="all" class="' + (this._category === "all" ? "selected" : "") + '">All categories</button>' + categories.map((category) => '<button data-category="' + this._escape(category) + '" class="' + (this._category === category ? "selected" : "") + '">' + this._escape(category) + '</button>').join("") + '</div>';
    const taskMarkup = filtered.length
      ? filtered.map((item) => this._renderTask(item, equipment)).join("")
      : '<div class="empty">No tasks match this filter.</div>';
    const equipmentMarkup = equipment.length
      ? equipment.map((item) => {
        const ids = item.attributes.task_ids || [];
        const linked = tasks.filter(({ state }) => ids.includes(state.attributes.task_id));
        const links = linked.length ? linked.map(({ state }) => '<button class="equipment-task" data-task-id="' + this._escape(state.attributes.task_id) + '">' + this._escape((state.attributes.friendly_name || state.entity_id).replace(/ Status$/, "")) + '</button>').join("") : '<span class="muted">No linked tasks</span>';
        return '<div class="equipment"><div><strong>' + this._escape(item.attributes.friendly_name || item.state) + '</strong><div class="equipment-links">' + links + '</div></div><span>' + this._escape(item.attributes.manufacturer || "") + " " + this._escape(item.attributes.model || "") + '</span></div>';
      }).join("")
      : '<div class="muted">No equipment records found.</div>';
    this.innerHTML = `
      <ha-card>
        <div class="header"><div class="title">${this._escape(this.config.title)}</div><div class="subtitle">Home maintenance at a glance</div></div>
        <div class="stats">
          <div class="stat"><strong>${this._escape(count("total"))}</strong><span>Active tasks</span></div>
          <div class="stat warning"><strong>${this._escape(count("overdue"))}</strong><span>Overdue</span></div>
          <div class="stat"><strong>${this._escape(count("due_today"))}</strong><span>Due today</span></div>
          <div class="stat"><strong>${this._escape(count("due_soon"))}</strong><span>Due soon</span></div>
        </div>
        <div class="filters">
          <button data-filter="all" class="${this._filter === "all" ? "selected" : ""}">All</button>
          <button data-filter="overdue" class="${this._filter === "overdue" ? "selected" : ""}">Overdue</button>
          <button data-filter="due_today" class="${this._filter === "due_today" ? "selected" : ""}">Due today</button>
          <button data-filter="upcoming" class="${this._filter === "upcoming" ? "selected" : ""}">Upcoming</button>
        </div>
        ${categoryMarkup}
        ${this._equipmentTask ? '<div class="active-filter">Showing selected equipment task <button data-clear-task>Clear</button></div>' : ""}
        <div class="tasks">${taskMarkup}</div>
        ${this.config.show_equipment ? `<section><h3>Equipment <small>${this._escape(count("equipment_count"))} registered</small></h3>${equipmentMarkup}</section>` : ""}
        ${this.config.show_history ? `<footer>Completion history records: <strong>${this._escape(count("history_count"))}</strong></footer>` : ""}
      </ha-card>
      <style>
        ha-card{overflow:hidden}.header{padding:18px 18px 10px}.title{font-size:1.35rem;font-weight:600}.subtitle,.meta,.muted{color:var(--secondary-text-color);font-size:.86rem}
        .stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;padding:8px 16px 14px}
        .stat{background:var(--secondary-background-color);border-radius:10px;padding:10px 6px;text-align:center;display:flex;flex-direction:column;gap:3px}
        .stat strong{font-size:1.35rem}.stat span{font-size:.75rem;color:var(--secondary-text-color)}.warning strong{color:var(--error-color)}
        .filters{display:flex;gap:6px;padding:0 16px 12px;flex-wrap:wrap}.filters button,.complete{border:0;border-radius:18px;padding:7px 11px;background:var(--secondary-background-color);color:var(--primary-text-color);cursor:pointer}
        .filters button.selected,.category-filters button.selected{background:var(--primary-color);color:var(--text-primary-color,#fff)}
        .category-filters{display:flex;gap:6px;padding:0 16px 10px;flex-wrap:wrap}.category-filters button,.equipment-task,.active-filter button{border:0;border-radius:16px;padding:6px 10px;background:var(--secondary-background-color);color:var(--primary-text-color);cursor:pointer;font:inherit;font-size:.8rem}.equipment-task,.active-filter button{background:none;color:var(--primary-color);text-decoration:underline;padding:3px 5px}.active-filter{padding:0 16px 10px;font-size:.82rem;color:var(--secondary-text-color)}
        .tasks{padding:0 16px}.task{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:13px 0;border-top:1px solid var(--divider-color)}
        .task-main{min-width:0}.task-name{font-weight:600}.meta{margin-top:3px}.description{font-size:.82rem;margin-top:5px;color:var(--secondary-text-color)}
        .details-toggle{border:0;background:none;color:var(--primary-color);padding:6px 0 0;cursor:pointer;font:inherit;font-size:.8rem}.task-details{margin-top:10px;padding:10px;border-radius:8px;background:var(--secondary-background-color);display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;font-size:.82rem}.task-details>div:not(.history-list){display:flex;flex-direction:column;gap:3px}.task-details span{color:var(--secondary-text-color)}.history-list{grid-column:1/-1;border-top:1px solid var(--divider-color);padding-top:8px}.history-item{display:flex;flex-direction:column;gap:2px;padding:7px 0;border-top:1px solid var(--divider-color)}
        .task-actions{display:flex;align-items:flex-end;gap:7px;flex-direction:column;flex-shrink:0}.status{font-size:.75rem;font-weight:600;border-radius:12px;padding:3px 8px;background:var(--secondary-background-color)}
        .status.overdue{color:var(--error-color)}.status.due_today{color:var(--warning-color)}.status.due_soon{color:var(--primary-color)}
        .complete{background:var(--success-color,var(--primary-color));color:var(--text-primary-color,#fff);font-size:.78rem}
        section{padding:8px 16px 14px;border-top:1px solid var(--divider-color)}h3{font-size:1rem;margin:8px 0}h3 small{font-weight:400;color:var(--secondary-text-color);margin-left:5px}
        .equipment{display:flex;justify-content:space-between;gap:12px;padding:7px 0;font-size:.88rem}.equipment span{color:var(--secondary-text-color);text-align:right}
        footer{border-top:1px solid var(--divider-color);padding:12px 16px;color:var(--secondary-text-color);font-size:.85rem}.empty{padding:16px 0;color:var(--secondary-text-color)}
        @media(max-width:420px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.task{align-items:flex-start}.task-actions{align-items:flex-end}.equipment{flex-direction:column;gap:2px}.equipment span{text-align:left}}
      </style>`;
    this.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => {
      this._filter = button.dataset.filter;
      this.render();
    }));
    this.querySelectorAll("[data-category]").forEach((button) => button.addEventListener("click", () => {
      this._category = button.dataset.category;
      this.render();
    }));
    this.querySelectorAll("[data-details]").forEach((button) => button.addEventListener("click", () => {
      this._detailTaskKey = this._detailTaskKey === button.dataset.details ? null : button.dataset.details;
      this.render();
    }));
    this.querySelectorAll("[data-task-id]").forEach((button) => button.addEventListener("click", () => {
      this._equipmentTask = button.dataset.taskId;
      this._category = "all";
      this._filter = "all";
      this.render();
    }));
    this.querySelectorAll("[data-clear-task]").forEach((button) => button.addEventListener("click", () => {
      this._equipmentTask = null;
      this.render();
    }));
    this.querySelectorAll("[data-complete-task]").forEach((button) => button.addEventListener("click", async () => {
      const notes = window.prompt("Add completion notes (optional):", "");
      if (notes === null) return;
      button.disabled = true;
      try {
        await this._hass.callService("home_maintenance_manager", "complete_task", {
          task_id: button.dataset.completeTask,
          integration_instance: button.dataset.instance,
          notes: notes.trim(),
        });
      } finally {
        button.disabled = false;
      }
    }));
  }
}
customElements.define("home-maintenance-manager-card", HomeMaintenanceManagerCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "home-maintenance-manager-card",
  name: "Home Maintenance Manager",
  description: "Maintenance overview with task status and completion actions.",
});
