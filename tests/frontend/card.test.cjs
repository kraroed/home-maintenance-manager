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
