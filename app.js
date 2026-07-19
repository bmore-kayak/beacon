async function main() {
  const response = await fetch(
    `data/latest.json?v=${Date.now()}`,
    {
      cache: "no-store",
    }
  );
  const data = await response.json();

  document.title = `Beacon • ${data.location}`;

  document.getElementById("overall").textContent =
    `${data.overall.status} ${data.overall.label}`;

  document.getElementById("note").textContent = data.note;

  document.getElementById("updated").textContent =
    `Updated ${formatUpdatedTime(data.updated)}`;

  const appLocation = document.getElementById("app-location");

  if (appLocation) {
    appLocation.textContent = data.location;
  }

  const container = document.getElementById("conditions");
  container.innerHTML = "";

  for (const [key, condition] of Object.entries(data.conditions)) {
    container.appendChild(renderCondition(key, condition));
  }
}


function windArrow(direction) {
  if (direction == null) {
    return "";
  }

  const rotation = (direction + 180) % 360;

  return `
    <span
      class="wind-arrow"
      style="--rotation:${rotation}deg"
      aria-hidden="true"
    >↑</span>
  `;
}

function cardinalDirection(degrees) {
  if (degrees == null) {
    return "";
  }

  const directions = [
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
  ];

  const normalized = ((degrees % 360) + 360) % 360;

  return directions[
    Math.round(normalized / 22.5) % 16
  ];
}


function windDirectionLabel(direction) {
  if (direction == null) {
    return "";
  }

  return `
    ${windArrow(direction)}
    ${cardinalDirection(direction)} ·
  `;
}

function renderCondition(key, condition) {
  const details = document.createElement("details");
  details.className = "condition";

  details.innerHTML = `
    <summary class="condition-row">
      <span class="condition-label">
        ${condition.icon} ${condition.label}
      </span>

      <span class="condition-detail">
        ${key === "wind" ? windDirectionLabel(condition.direction_deg) : ""}
        ${condition.detail}
      </span>
      
      <span class="condition-status">
        ${condition.status}
      </span>

      <span class="chevron">▾</span>
    </summary>

    <div class="condition-details">
      ${renderDetails(key, condition)}
    </div>
  `;

  return details;
}


function renderDetails(key, condition) {
  let content = "";

  if (key === "advisories") {
    content += renderAdvisories(condition.items);
  }

  if (key === "wind") {
    content += renderWindDetails(condition);
  }

  if (key === "rainfall" && condition.message) {
    content += `
      <div class="expanded-note">
        ${condition.message}
      </div>
    `;
  }

  if (key === "bacteria") {
    content += renderStations(condition.stations);
  }

  if (key === "club_notices") {
    content += renderClubNotices(condition);
  }

  if (
    !["advisories", "wind", "rainfall", "bacteria", "club_notices"].includes(key) &&
    condition.detail
  ) {
    content += `
      <div class="expanded-note">
        ${condition.detail}
      </div>
    `;
  }

  content += renderSource(key, condition.source);

  return content;
}


function renderAdvisories(items = []) {
  if (!items.length) {
    return `
      <div class="expanded-empty">
        No active advisories.
      </div>
    `;
  }

  return `
    <div class="advisory-list">
      ${items.map(item => `
        <div class="advisory-item">
          <span class="advisory-name">
            ${item.event}
          </span>

          <span class="advisory-time">
            ${formatAlertTime(item)}
          </span>

          <span class="advisory-status">
            ${item.status}
          </span>
        </div>
      `).join("")}
    </div>
  `;
}

function renderWindDetails(condition) {
  const direction = condition.direction_deg;

  return `
    <div class="wind-details">
      <div class="wind-detail-item">
        <div class="wind-detail-label">Direction</div>

        <div class="wind-direction-value">
          ${direction != null ? windArrow(direction) : ""}

          <span>
            ${direction != null
              ? `${cardinalDirection(direction)} · ${Math.round(direction)}°`
              : "Unavailable"}
          </span>
        </div>
      </div>

      <div class="wind-detail-item">
        <div class="wind-detail-label">Sustained</div>

        <div class="wind-detail-value">
          ${condition.speed_kt ?? "—"} kt
        </div>
      </div>

      <div class="wind-detail-item">
        <div class="wind-detail-label">Gusts</div>

        <div class="wind-detail-value">
          ${condition.gust_kt ?? "—"} kt
        </div>
      </div>
    </div>
  `;
}

function renderClubNotices(condition) {
  const items = condition.items || [];

  if (!items.length) {
    return `
      <div class="expanded-empty">
        ${
          condition.detail === "Club events unavailable"
            ? "Club events are currently unavailable."
            : "No upcoming club events."
        }
      </div>
    `;
  }

  return `
    <div class="club-event-list">
      ${items.map(item => `
        <a
          class="club-event-item ${item.notice ? "club-event-notice" : ""}"
          href="${item.source_url}"
          target="_blank"
          rel="noopener"
        >
          <div class="club-event-header">
            <div class="club-event-title">
              ${item.title}
            </div>

            ${
              item.notice
                ? `<div class="club-event-status">🟡</div>`
                : ""
            }
          </div>

          <div class="club-event-summary">
            ${item.summary}
          </div>

          <div class="club-event-time">
            ${formatEventWindow(
              item.starts_at,
              item.ends_at
            )}
          </div>
        </a>
      `).join("")}
    </div>
  `;
}


function renderStations(stations = []) {
  if (!stations.length) {
    return `<div class="expanded-empty">No station data available.</div>`;
  }

  const regions = {};

  for (const station of stations) {
    const region = station.region || "Other";

    if (!regions[region]) {
      regions[region] = [];
    }

    regions[region].push(station);
  }

  return `
    <div class="stations">
      ${Object.entries(regions).map(([region, regionStations]) => {
        const summary = summarizeRegion(regionStations);
        const open = regionIsOpen(region);

        return `
          <details
            class="station-region"
            data-region="${region}"
            ${open ? "open" : ""}
          >
            <summary class="station-region-summary">
              <span class="station-region-label">
                ${region}
              </span>
            
              <span class="station-region-range">
                ${summary.detail}
              </span>
            
              <span class="station-region-status">
                ${summary.status}
              </span>
            
              <span class="region-chevron">▾</span>
            </summary>

            <div class="station-region-content">
              ${regionStations.map(station => `
                <div class="station">
                  <div class="station-info">
                    <div class="station-name">
                      ${station.site}
                    </div>

                    <div class="station-date">
                      ${station.date
                        ? `Sampled ${formatSampleDate(station.date)}`
                        : "Sample date unavailable"}
                    </div>
                  </div>

                  <div class="station-reading">
                    <span class="station-value">
                      ${station.bacteria ?? "—"} MPN
                    </span>
                  
                    <span class="station-status">
                      ${station.status}
                    </span>
                  </div>
                </div>
              `).join("")}
            </div>
          </details>
        `;
      }).join("")}
    </div>
  `;
}


function summarizeRegion(stations) {
  const current = stations.filter(
    station =>
      !station.stale &&
      station.bacteria != null
  );

  if (!current.length) {
    return {
      status: "⚪",
      detail: "Outdated",
    };
  }

  const counts = current.map(
    station => station.bacteria
  );

  const rank = {
    "🟢": 0,
    "🟡": 1,
    "🟠": 2,
    "🔴": 3,
  };

  const status = current.reduce(
    (highest, station) =>
      rank[station.status] > rank[highest]
        ? station.status
        : highest,
    "🟢"
  );

  const minimum = Math.min(...counts);
  const maximum = Math.max(...counts);

  return {
    status,
    detail:
      minimum === maximum
        ? `${minimum} MPN`
        : `${minimum}–${maximum} MPN`,
  };
}


function regionIsOpen(region) {
  const saved = localStorage.getItem(
    `beacon-region-${region}`
  );

  if (saved !== null) {
    return saved === "open";
  }

  return false;
}


function renderSource(key, source) {
  if (!source) {
    return "";
  }

  if (source.label && source.url) {
    return `
      <div class="detail-footer">
        <div>
          <a
            href="${source.url}"
            target="_blank"
            rel="noopener"
          >
            ${source.label}
          </a>
        </div>
      </div>
    `;
  }

  const providers = source.provider
    ? source.provider.split(" · ")
    : [];

  return `
    <div class="detail-footer">
      ${source.location
        ? `<div>${source.location}</div>`
        : ""}

      ${providers.map(provider => `
        <div>${provider}</div>
      `).join("")}

      ${source.updated
        ? `
          <div>
            ${key === "bacteria" ? "Latest sample" : "Updated"}
            ${formatDate(source.updated)}
          </div>
        `
        : ""}
    </div>
  `;
}


function formatSampleDate(value) {
  const date = new Date(value);

  return date.toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: date.getFullYear() === new Date().getFullYear()
      ? undefined
      : "numeric",
  });
}


function timeOptions(date, extra = {}) {
  return {
    hour: "numeric",
    minute: date.getMinutes() === 0
      ? undefined
      : "2-digit",
    ...extra,
  };
}

function formatDate(value) {
  const date = new Date(value);

  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    ...timeOptions(date),
  });
}

function formatAlertTime(item) {
  const starts = item.starts
    ? new Date(item.starts)
    : null;

  const ends = item.ends
    ? new Date(item.ends)
    : null;

  const now = new Date();

  const time = date =>
    date.toLocaleTimeString(
      [],
      timeOptions(date)
    );

  if (starts && ends) {
    return starts <= now
      ? `Until ${time(ends)}`
      : `${time(starts)}–${time(ends)}`;
  }

  if (ends) {
    return `Until ${time(ends)}`;
  }

  if (starts) {
    return `Beginning ${time(starts)}`;
  }

  return "Time not specified";
}


function formatEventWindow(startValue, endValue) {
  const start = new Date(startValue);
  const end = new Date(endValue);

  const date = start.toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
  });

  const startTime = start.toLocaleTimeString(
    [],
    timeOptions(start)
  );

  const endTime = end.toLocaleTimeString(
    [],
    timeOptions(end)
  );

  return `${date} · ${startTime}–${endTime}`;
}


function formatUpdatedTime(value) {
  const date = new Date(value);

  return date.toLocaleTimeString(
    [],
    timeOptions(date, {
      timeZoneName: "short",
    })
  );
}


document.addEventListener(
  "toggle",
  event => {
    const details = event.target;

    if (!details.matches(".station-region")) {
      return;
    }

    const region = details.dataset.region;

    localStorage.setItem(
      `beacon-region-${region}`,
      details.open ? "open" : "closed"
    );
  },
  true
);


main();
