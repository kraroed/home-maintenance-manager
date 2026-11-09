const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "../../www/home-maintenance-manager-card.js"),
  "utf8"
);

class HTMLElement {}
let Card;
const customCards = [];
const context = {
  HTMLElement,
  customElements: {
    define(name, constructor) {
      assert.equal(name, "home-maintenance-manager-card");
      Card = constructor;
    },
  },
  window: { customCards },
};

vm.runInNewContext(source, context, { filename: "home-maintenance-manager-card.js" });

test("registers the Lovelace card and its metadata", () => {
  assert.equal(typeof Card, "function");
  assert.equal(customCards.length, 1);
  assert.equal(customCards[0].type, "home-maintenance-manager-card");
});

test("escapes HTML-sensitive values before rendering", () => {
  const card = new Card();
  assert.equal(
    card._escape('<script>alert("x")</script> & \'quoted\''),
    "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &#39;quoted&#39;"
  );
});

test("builds stable local calendar date keys", () => {
  const card = new Card();
  assert.equal(card._calendarKey(new Date(2026, 0, 5)), "2026-01-05");
});

test("renders a Monday-first calendar with navigation controls", () => {
  const card = new Card();
  card._calendarMonth = new Date(2026, 10, 1);
  card._selectedCalendarDate = "2026-11-08";

  const markup = card._renderCalendar([], []);

  assert.match(markup, /data-calendar-prev/);
  assert.match(markup, /data-calendar-next/);
  assert.match(markup, /data-calendar-today/);
  assert.match(markup, /Mon/);
  assert.match(markup, /Sun/);
  assert.match(markup, /November 2026/);
});

test("history search filters records and escapes user-provided notes", () => {
  const card = new Card();
  card._historySearch = "boiler";
  card._historyFrom = "";
  card._historyTo = "";

  const tasks = [
    {
      state: {
        entity_id: "sensor.boiler_status",
        attributes: {
          task_id: "boiler_service",
          friendly_name: "Boiler service Status",
          completion_history: [
            {
              history_id: "record-1",
              completed_at: "2026-11-08T12:00:00Z",
              notes: '<img src=x onerror="alert(1)">',
              attachments: ["/local/boiler.jpg"],
              total_cost: 42,
            },
          ],
        },
      },
    },
    {
      state: {
        entity_id: "sensor.gutter_status",
        attributes: {
          task_id: "clean_gutters",
          friendly_name: "Clean gutters Status",
          completion_history: [
            { history_id: "record-2", completed_at: "2026-11-07T12:00:00Z" },
          ],
        },
      },
    },
  ];

  const markup = card._renderHistory(tasks, []);

  assert.match(markup, /Showing 1 of 2 recent completion records/);
  assert.match(markup, /Boiler service/);
  assert.doesNotMatch(markup, /Clean gutters/);
  assert.match(markup, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  assert.doesNotMatch(markup, /<img src=x/);
});


function createInteractiveCard(selector, dataset, prompts) {
  const control = {
    dataset,
    disabled: false,
    handlers: {},
    addEventListener(name, callback) {
      this.handlers[name] = callback;
    },
  };
  const card = new Card();
  card.querySelectorAll = (query) => query === selector ? [control] : [];
  const calls = [];
  card.setConfig({});
  card.hass = {
    states: {},
    async callService(domain, service, data) {
      calls.push({ domain, service, data });
    },
  };
  context.window.prompt = () => prompts.shift() ?? null;
  context.window.alert = () => {};
  return { card, control, calls };
}

test("reschedule action calls the service with the selected date and reason", async () => {
  const { control, calls } = createInteractiveCard(
    "[data-reschedule-task]",
    { rescheduleTask: "clean_gutters", instance: "main", currentDue: "2026-11-15" },
    ["2026-11-22", "Weather delay"]
  );

  await control.handlers.click();

  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [{
    domain: "home_maintenance_manager",
    service: "reschedule_task",
    data: {
      task_id: "clean_gutters",
      integration_instance: "main",
      due_date: "2026-11-22",
      reason: "Weather delay",
    },
  }]);
  assert.equal(control.disabled, false);
});

test("complete action forwards notes, attachment references, and costs", async () => {
  const { control, calls } = createInteractiveCard(
    "[data-complete-task]",
    { completeTask: "replace_filter", instance: "main" },
    ["Replaced filter", "/local/filter.jpg\\nhttps://example.com/receipt", "25.50", "18.75"]
  );

  await control.handlers.click();

  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [{
    domain: "home_maintenance_manager",
    service: "complete_task",
    data: {
      task_id: "replace_filter",
      integration_instance: "main",
      notes: "Replaced filter",
      attachments: "/local/filter.jpg\\nhttps://example.com/receipt",
      labor_cost: 25.5,
      parts_cost: 18.75,
    },
  }]);
  assert.equal(control.disabled, false);
});

test("canceling a task action does not call a Home Assistant service", async () => {
  const { control, calls } = createInteractiveCard(
    "[data-reschedule-task]",
    { rescheduleTask: "clean_gutters", instance: "main", currentDue: "2026-11-15" },
    [null]
  );

  await control.handlers.click();

  assert.deepEqual(calls, []);
});


test("invalid reschedule date format is rejected before calling the service", async () => {
  const { control, calls } = createInteractiveCard(
    "[data-reschedule-task]",
    { rescheduleTask: "clean_gutters", instance: "main", currentDue: "2026-11-15" },
    ["11/22/2026"]
  );
  let alertMessage = "";
  context.window.alert = (message) => { alertMessage = message; };

  await control.handlers.click();

  assert.deepEqual(calls, []);
  assert.equal(alertMessage, "Enter a real calendar date as YYYY-MM-DD.");
});

test("canceling the reason prompt prevents rescheduling", async () => {
  const { control, calls } = createInteractiveCard(
    "[data-reschedule-task]",
    { rescheduleTask: "clean_gutters", instance: "main", currentDue: "2026-11-15" },
    ["2026-11-22", null]
  );

  await control.handlers.click();

  assert.deepEqual(calls, []);
  assert.equal(control.disabled, false);
});

test("action button is re-enabled when a Home Assistant service call fails", async () => {
  const { card, control } = createInteractiveCard(
    "[data-complete-task]",
    { completeTask: "replace_filter", instance: "main" },
    ["Done", "", "0", "0"]
  );
  card._hass.callService = async () => {
    throw new Error("Service unavailable");
  };

  await assert.rejects(control.handlers.click(), /Service unavailable/);
  assert.equal(control.disabled, false);
});


test("validates real calendar dates and rejects impossible dates", () => {
  const card = new Card();

  assert.equal(card._isValidDateKey("2028-02-29"), true);
  assert.equal(card._isValidDateKey("2026-02-28"), true);
  assert.equal(card._isValidDateKey("2026-02-30"), false);
  assert.equal(card._isValidDateKey("2026-13-01"), false);
  assert.equal(card._isValidDateKey("2026-04-31"), false);
  assert.equal(card._isValidDateKey("not-a-date"), false);
});

test("impossible reschedule date is rejected before prompting for a reason", async () => {
  const { control, calls } = createInteractiveCard(
    "[data-reschedule-task]",
    { rescheduleTask: "clean_gutters", instance: "main", currentDue: "2026-11-15" },
    ["2026-02-30"]
  );
  let alertMessage = "";
  context.window.alert = (message) => { alertMessage = message; };

  await control.handlers.click();

  assert.deepEqual(calls, []);
  assert.equal(alertMessage, "Enter a real calendar date as YYYY-MM-DD.");
});
