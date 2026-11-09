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
    if (this._view === undefined) this._view = "list";
    if (this._calendarMonth === undefined) this._calendarMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
    if (this._selectedCalendarDate === undefined) this._selectedCalendarDate = this._calendarKey(new Date());
    if (this._historySearch === undefined) this._historySearch = "";
    if (this._historyFrom === undefined) this._historyFrom = "";
    if (this._historyTo === undefined) this._historyTo = "";
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

  _money(value) {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" })
      .format(Number(value || 0));
  }


  _calendarKey(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  _renderCalendar(tasks, equipment) {
    const month = new Date(this._calendarMonth.getFullYear(), this._calendarMonth.getMonth(), 1);
    const monthLabel = month.toLocaleDateString(undefined, { month: "long", year: "numeric" });
    const firstDay = new Date(month.getFullYear(), month.getMonth(), 1);
    const mondayOffset = (firstDay.getDay() + 6) % 7;
    const gridStart = new Date(month.getFullYear(), month.getMonth(), 1 - mondayOffset);
    const dueByDate = new Map();
    tasks.forEach((item) => {
      const value = item.state.attributes?.next_due;
      if (!value) return;
      const due = new Date(value);
      if (Number.isNaN(due.getTime())) return;
      const key = this._calendarKey(due);
      if (!dueByDate.has(key)) dueByDate.set(key, []);
      dueByDate.get(key).push(item);
    });
    const selectedTasks = dueByDate.get(this._selectedCalendarDate) || [];
    const cells = Array.from({ length: 42 }, (_, index) => {
      const date = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + index);
      const key = this._calendarKey(date);
      const items = dueByDate.get(key) || [];
      const outside = date.getMonth() !== month.getMonth();
      const selected = key === this._selectedCalendarDate;
      const labels = items.slice(0, 2).map((item) => {
        const name = (item.state.attributes.friendly_name || item.state.entity_id).replace(/ Status$/, "");
        return `<span class="calendar-task">${this._escape(name)}</span>`;
      }).join("");
      const more = items.length > 2 ? `<span class="calendar-more">+${items.length - 2} more</span>` : "";
      return `<button class="calendar-day ${outside ? "outside" : ""} ${selected ? "selected" : ""} ${items.length ? "has-tasks" : ""}" data-calendar-date="${key}">
        <strong>${date.getDate()}</strong>${labels}${more}
      </button>`;
    }).join("");
    const selectedDate = new Date(this._selectedCalendarDate + "T12:00:00");
    const selectedLabel = selectedDate.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
    const selectedMarkup = selectedTasks.length
      ? selectedTasks.map((item) => this._renderTask(item, equipment)).join("")
      : '<div class="empty">No maintenance tasks are due on this date.</div>';
    return `<section class="calendar-section">
      <div class="calendar-toolbar">
        <button data-calendar-prev aria-label="Previous month">‹</button>
        <strong>${this._escape(monthLabel)}</strong>
        <button data-calendar-next aria-label="Next month">›</button>
        <button data-calendar-today>Today</button>
      </div>
      <div class="calendar-grid">
        ${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => `<div class="calendar-weekday">${day}</div>`).join("")}
        ${cells}
      </div>
      <div class="calendar-selected"><h3>${this._escape(selectedLabel)}</h3>${selectedMarkup}</div>
    </section>`;
  }


  _renderHistory(tasks, equipment) {
    const records = [];
    tasks.forEach(({ state }) => {
      const attrs = state.attributes || {};
      (attrs.completion_history || []).forEach((record) => {
        const names = (record.equipment_ids || []).map((id) => equipment.find((entry) =>
          entry.attributes.equipment_id === id &&
          (entry.attributes.integration_instance || "default") === (attrs.integration_instance || "default")
        )).filter(Boolean).map((entry) => entry.attributes.friendly_name || entry.state);
        records.push({...record, task_id: attrs.task_id,
          task_name: record.task_name || (attrs.friendly_name || state.entity_id).replace(/ Status$/, ""),
          equipment_names: names});
      });
    });
    const unique = [...new Map(records.map((record) => [record.history_id || `${record.task_id}:${record.completed_at}`, record])).values()]
      .sort((a,b) => new Date(b.completed_at) - new Date(a.completed_at));
    const filtered = unique.filter((record) => {
      const haystack = [record.task_name, record.task_id, record.notes, ...(record.equipment_names || [])].join(" ").toLowerCase();
      if (this._historySearch && !haystack.includes(this._historySearch.toLowerCase())) return false;
      const day = (record.completed_at || "").slice(0,10);
      return (!this._historyFrom || day >= this._historyFrom) && (!this._historyTo || day <= this._historyTo);
    });
    const rows = filtered.length ? filtered.map((record) => `
      <article class="history-record">
        <div class="history-record-heading"><strong>${this._escape(record.task_name)}</strong><span>${this._escape(this._date(record.completed_at))}</span></div>
        ${record.equipment_names?.length ? `<div class="history-meta">Equipment: ${this._escape(record.equipment_names.join(", "))}</div>` : ""}
        ${record.notes ? `<p>${this._escape(record.notes)}</p>` : ""}
        <div class="history-costs">Labor: ${this._money(record.labor_cost)} · Parts: ${this._money(record.parts_cost)} · Total: <strong>${this._money(record.total_cost)}</strong></div>
        ${(record.attachments || []).length ? `<div class="history-attachments">${record.attachments.map((url) => `<a href="${this._escape(url)}" target="_blank" rel="noopener noreferrer">View attachment</a>`).join(" · ")}</div>` : ""}
      </article>`).join("") : '<div class="empty">No completion records match these filters.</div>';
    return `<section class="history-view">
      <div class="history-controls">
        <input type="search" data-history-search placeholder="Search task, equipment, or notes" value="${this._escape(this._historySearch)}">
        <label>From <input type="date" data-history-from value="${this._escape(this._historyFrom)}"></label>
        <label>To <input type="date" data-history-to value="${this._escape(this._historyTo)}"></label>
        <button data-history-clear>Clear filters</button>
      </div>
      <div class="history-result-count">Showing ${filtered.length} of ${unique.length} recent completion records</div>
      <div class="history-records">${rows}</div>
      <p class="history-note">The card displays recent completion records available from task sensors. Use Export history for the complete permanent archive.</p>
    </section>`;
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
      ? `<div class="task-action-buttons"><button class="reschedule" data-reschedule-task="${this._escape(attrs.task_id)}" data-instance="${this._escape(attrs.integration_instance || "default")}" data-current-due="${this._escape((attrs.next_due || "").slice(0, 10))}">Reschedule</button><button class="complete" data-complete-task="${this._escape(attrs.task_id)}" data-instance="${this._escape(attrs.integration_instance || "default")}">Mark complete</button></div>`
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
    const scheduleHistory = [...(attrs.schedule_history || [])].reverse();
    const scheduleMarkup = scheduleHistory.length ? `<div class="schedule-history"><strong>Recent schedule changes</strong>${scheduleHistory.slice(0, 5).map((record) => `<div class="history-item"><span>${this._escape(this._date(record.adjusted_at))}: ${this._escape(this._date(record.previous_due))} → ${this._escape(this._date(record.next_due))}</span>${record.reason ? `<span>${this._escape(record.reason)}</span>` : ""}</div>`).join("")}</div>` : "";
    const historyMarkup = history.length ? history.slice(0, 5).map((record) => `
      <div class="history-item">
        <strong>${this._escape(this._date(record.completed_at))}</strong>
        <span>Previous due: ${this._escape(this._date(record.previous_due))}</span>
        ${record.notes ? `<div class="description">${this._escape(record.notes)}</div>` : ""}
        <span>Labor: ${this._money(record.labor_cost)} · Parts: ${this._money(record.parts_cost)} · Total: <strong>${this._money(record.total_cost)}</strong></span>
        ${(record.attachments || []).length ? `<div class="history-attachments">${record.attachments.map((url) => `<a href="${this._escape(url)}" target="_blank" rel="noopener noreferrer">View attachment</a>`).join(" · ")}</div>` : ""}
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
      ${scheduleMarkup}
    </div>`;
  }

  render() {
    if (!this._hass || !this.config) return;
    const { tasks, summaries, equipment } = this._discover();
    const count = (key) => summaries.get(key) ?? "—";
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
    const calendarMarkup = this._renderCalendar(tasks, equipment);
    const historyMarkup = this._renderHistory(tasks, equipment);
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
        <div class="view-toggle"><button data-view="list" class="${this._view === "list" ? "selected" : ""}">List view</button><button data-view="calendar" class="${this._view === "calendar" ? "selected" : ""}">Calendar view</button><button data-view="history" class="${this._view === "history" ? "selected" : ""}">History</button></div>
        <div class="filters" style="${this._view !== "list" ? "display:none" : ""}">
          <button data-filter="all" class="${this._filter === "all" ? "selected" : ""}">All</button>
          <button data-filter="overdue" class="${this._filter === "overdue" ? "selected" : ""}">Overdue</button>
          <button data-filter="due_today" class="${this._filter === "due_today" ? "selected" : ""}">Due today</button>
          <button data-filter="upcoming" class="${this._filter === "upcoming" ? "selected" : ""}">Upcoming</button>
        </div>
        ${this._view === "calendar" ? calendarMarkup : this._view === "history" ? historyMarkup : categoryMarkup}
        ${this._equipmentTask ? '<div class="active-filter">Showing selected equipment task <button data-clear-task>Clear</button></div>' : ""}
        ${this._view === "list" ? `<div class="tasks">${taskMarkup}</div>` : ""}
        ${this.config.show_equipment ? `<section><h3>Equipment <small>${this._escape(count("equipment_count"))} registered</small></h3>${equipmentMarkup}</section>` : ""}
        ${this.config.show_history ? `<footer>Completion history records: <strong>${this._escape(count("history_count"))}</strong></footer>` : ""}
      </ha-card>
      <style>
        ha-card{overflow:hidden}.header{padding:18px 18px 10px}.title{font-size:1.35rem;font-weight:600}.subtitle,.meta,.muted{color:var(--secondary-text-color);font-size:.86rem}
        .stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;padding:8px 16px 14px}
        .stat{background:var(--secondary-background-color);border-radius:10px;padding:10px 6px;text-align:center;display:flex;flex-direction:column;gap:3px}
        .stat strong{font-size:1.35rem}.stat span{font-size:.75rem;color:var(--secondary-text-color)}.warning strong{color:var(--error-color)}
        .view-toggle{display:flex;gap:7px;padding:0 16px 12px}.view-toggle button,.calendar-toolbar button{border:0;border-radius:16px;padding:7px 12px;background:var(--secondary-background-color);color:var(--primary-text-color);cursor:pointer}.view-toggle button.selected{background:var(--primary-color);color:var(--text-primary-color,#fff)}
        .calendar-section{padding:8px 12px 14px}.calendar-toolbar{display:flex;align-items:center;justify-content:center;gap:12px;padding:6px 0 12px}.calendar-toolbar strong{min-width:150px;text-align:center}.calendar-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:3px}.calendar-weekday{text-align:center;font-size:.72rem;color:var(--secondary-text-color);padding:5px 0}.calendar-day{min-width:0;min-height:74px;padding:4px;border:1px solid var(--divider-color);border-radius:7px;background:var(--card-background-color);color:var(--primary-text-color);text-align:left;display:flex;flex-direction:column;gap:3px;cursor:pointer}.calendar-day>strong{font-size:.8rem}.calendar-day.outside{opacity:.42}.calendar-day.selected{outline:2px solid var(--primary-color);background:var(--secondary-background-color)}.calendar-day.has-tasks>strong{color:var(--primary-color)}.calendar-task,.calendar-more{font-size:.62rem;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border-radius:3px;background:var(--secondary-background-color);padding:2px}.calendar-more{color:var(--secondary-text-color)}.calendar-selected{padding-top:10px}.calendar-selected h3{margin-bottom:6px}
        .filters{display:flex;gap:6px;padding:0 16px 12px;flex-wrap:wrap}.filters button,.complete{border:0;border-radius:18px;padding:7px 11px;background:var(--secondary-background-color);color:var(--primary-text-color);cursor:pointer}
        .filters button.selected,.category-filters button.selected{background:var(--primary-color);color:var(--text-primary-color,#fff)}
        .category-filters{display:flex;gap:6px;padding:0 16px 10px;flex-wrap:wrap}.category-filters button,.equipment-task,.active-filter button{border:0;border-radius:16px;padding:6px 10px;background:var(--secondary-background-color);color:var(--primary-text-color);cursor:pointer;font:inherit;font-size:.8rem}.equipment-task,.active-filter button{background:none;color:var(--primary-color);text-decoration:underline;padding:3px 5px}.active-filter{padding:0 16px 10px;font-size:.82rem;color:var(--secondary-text-color)}
        .tasks{padding:0 16px}.task{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:13px 0;border-top:1px solid var(--divider-color)}
        .task-main{min-width:0}.task-name{font-weight:600}.meta{margin-top:3px}.description{font-size:.82rem;margin-top:5px;color:var(--secondary-text-color)}
        .details-toggle{border:0;background:none;color:var(--primary-color);padding:6px 0 0;cursor:pointer;font:inherit;font-size:.8rem}.task-details{margin-top:10px;padding:10px;border-radius:8px;background:var(--secondary-background-color);display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;font-size:.82rem}.task-details>div:not(.history-list){display:flex;flex-direction:column;gap:3px}.task-details span{color:var(--secondary-text-color)}.history-list{grid-column:1/-1;border-top:1px solid var(--divider-color);padding-top:8px}.history-item{display:flex;flex-direction:column;gap:2px;padding:7px 0;border-top:1px solid var(--divider-color)}.history-attachments{font-size:.8rem}.history-attachments a{color:var(--primary-color);margin-right:6px}
        .history-view{padding:10px 16px 16px}.history-controls{display:grid;grid-template-columns:1fr 1fr;gap:8px;align-items:end}.history-controls>input,.history-controls label input{box-sizing:border-box;width:100%;min-width:0;border:1px solid var(--divider-color);border-radius:7px;padding:9px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit}.history-controls>input{grid-column:1/-1}.history-controls label{font-size:.78rem;color:var(--secondary-text-color)}.history-controls label input{display:block;margin-top:3px}.history-controls button{justify-self:start;border:0;background:var(--secondary-background-color);color:var(--primary-text-color);border-radius:16px;padding:7px 12px;cursor:pointer}.history-result-count{font-size:.8rem;color:var(--secondary-text-color);padding:12px 0 4px}.history-record{border-top:1px solid var(--divider-color);padding:11px 0;font-size:.85rem}.history-record-heading{display:flex;justify-content:space-between;gap:8px}.history-record-heading span,.history-meta{color:var(--secondary-text-color);font-size:.8rem}.history-record p{margin:6px 0}.history-costs{font-size:.8rem}.history-note{font-size:.75rem;color:var(--secondary-text-color);margin-top:12px}
        .task-actions{display:flex;align-items:flex-end;gap:7px;flex-direction:column;flex-shrink:0}.status{font-size:.75rem;font-weight:600;border-radius:12px;padding:3px 8px;background:var(--secondary-background-color)}
        .status.overdue{color:var(--error-color)}.status.due_today{color:var(--warning-color)}.status.due_soon{color:var(--primary-color)}
        .task-action-buttons{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}.reschedule{border:1px solid var(--divider-color);border-radius:18px;padding:7px 10px;background:var(--card-background-color);color:var(--primary-color);font-size:.78rem;cursor:pointer}.complete{background:var(--success-color,var(--primary-color));color:var(--text-primary-color,#fff);font-size:.78rem}
        section{padding:8px 16px 14px;border-top:1px solid var(--divider-color)}h3{font-size:1rem;margin:8px 0}h3 small{font-weight:400;color:var(--secondary-text-color);margin-left:5px}
        .equipment{display:flex;justify-content:space-between;gap:12px;padding:7px 0;font-size:.88rem}.equipment span{color:var(--secondary-text-color);text-align:right}
        footer{border-top:1px solid var(--divider-color);padding:12px 16px;color:var(--secondary-text-color);font-size:.85rem}.empty{padding:16px 0;color:var(--secondary-text-color)}
        @media(max-width:600px){.calendar-day{min-height:58px;padding:3px}.calendar-task{font-size:.55rem}.calendar-more{font-size:.55rem}}
        @media(max-width:420px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.task{align-items:flex-start}.task-actions{align-items:flex-end}.equipment{flex-direction:column;gap:2px}.equipment span{text-align:left}}
      </style>`;
    this.querySelectorAll("[data-history-search]").forEach((input) => input.addEventListener("input", () => {
      this._historySearch = input.value;
      const position = input.selectionStart;
      this.render();
      const refreshed = this.querySelector("[data-history-search]");
      if (refreshed) { refreshed.focus(); refreshed.setSelectionRange(position, position); }
    }));
    this.querySelectorAll("[data-history-from]").forEach((input) => input.addEventListener("change", () => {
      this._historyFrom = input.value; this.render();
    }));
    this.querySelectorAll("[data-history-to]").forEach((input) => input.addEventListener("change", () => {
      this._historyTo = input.value; this.render();
    }));
    this.querySelectorAll("[data-history-clear]").forEach((button) => button.addEventListener("click", () => {
      this._historySearch = ""; this._historyFrom = ""; this._historyTo = ""; this.render();
    }));
    this.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => {
      this._view = button.dataset.view;
      this.render();
    }));
    this.querySelectorAll("[data-calendar-prev]").forEach((button) => button.addEventListener("click", () => {
      this._calendarMonth = new Date(this._calendarMonth.getFullYear(), this._calendarMonth.getMonth() - 1, 1);
      this.render();
    }));
    this.querySelectorAll("[data-calendar-next]").forEach((button) => button.addEventListener("click", () => {
      this._calendarMonth = new Date(this._calendarMonth.getFullYear(), this._calendarMonth.getMonth() + 1, 1);
      this.render();
    }));
    this.querySelectorAll("[data-calendar-today]").forEach((button) => button.addEventListener("click", () => {
      const today = new Date();
      this._calendarMonth = new Date(today.getFullYear(), today.getMonth(), 1);
      this._selectedCalendarDate = this._calendarKey(today);
      this.render();
    }));
    this.querySelectorAll("[data-calendar-date]").forEach((button) => button.addEventListener("click", () => {
      this._selectedCalendarDate = button.dataset.calendarDate;
      this.render();
    }));
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
    this.querySelectorAll("[data-reschedule-task]").forEach((button) => button.addEventListener("click", async () => {
      const currentDue = button.dataset.currentDue || this._calendarKey(new Date());
      const dueDate = window.prompt("New due date (YYYY-MM-DD):", currentDue);
      if (dueDate === null || !/^\d{4}-\d{2}-\d{2}$/.test(dueDate.trim())) {
        if (dueDate !== null) window.alert("Enter the date as YYYY-MM-DD.");
        return;
      }
      const reason = window.prompt("Why is this task being rescheduled? (optional)", "");
      if (reason === null) return;
      button.disabled = true;
      try {
        await this._hass.callService("home_maintenance_manager", "reschedule_task", {
          task_id: button.dataset.rescheduleTask,
          integration_instance: button.dataset.instance,
          due_date: dueDate.trim(),
          reason: reason.trim(),
        });
      } finally {
        button.disabled = false;
      }
    }));
    this.querySelectorAll("[data-complete-task]").forEach((button) => button.addEventListener("click", async () => {
      const notes = window.prompt("Add completion notes (optional):", "");
      if (notes === null) return;
      const attachments = window.prompt(
        "Add photo or receipt URLs, one per line. Upload files to /config/www/ first and use /local/ paths. Leave blank if none.",
        ""
      );
      if (attachments === null) return;
      const laborCost = window.prompt("Labor or service cost in USD (optional):", "0");
      if (laborCost === null) return;
      const partsCost = window.prompt("Parts and materials cost in USD (optional):", "0");
      if (partsCost === null) return;
      button.disabled = true;
      try {
        await this._hass.callService("home_maintenance_manager", "complete_task", {
          task_id: button.dataset.completeTask,
          integration_instance: button.dataset.instance,
          notes: notes.trim(),
          attachments: attachments.trim(),
          labor_cost: Number(laborCost || 0),
          parts_cost: Number(partsCost || 0),
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
