async function main() {
  const response = await fetch("data/latest.json");
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


function renderCondition(key, condition) {
  const details = document.createElement("details");
  details.className = "condition";

  details.innerHTML = `
    <summary class="condition-row">
      <span class="condition-label">
        ${condition.icon} ${condition.label}
      </span>

      <span class="condition-detail">
        ${key === "wind" ? windArrow(condition.direction_deg) : ""}
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
    content += renderClubNotices(condition.items);
  }

  content += renderSource(key, condition.source);

  return content;
}


function renderAdvisories(items = []) {
  if (!items.length) {
    return `<div class="expanded-empty">No active advisories.</div>`;
  }

  return `
    <div class="advisory-list">
      ${items.map(item => `
        <div class="advisory-item">
          <span>${item.event}</span>

          ${item.ends
            ? `<span>Until ${formatTime(item.ends)}</span>`
            : ""}
        </div>
      `).join("")}
    </div>
  `;
}


function renderClubNotices(items = []) {
  if (!items.length) {
    return `
      <div class="expanded-empty">
        No upcoming club events.
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
          <div class="club-event-title">
            ${item.notice ? "🟡 " : ""}${item.title}
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

              <span class="station-region-status">
                ${summary.status}
              </span>

              <span class="station-region-range">
                ${summary.detail}
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
                    ${station.status}
                    ${station.bacteria ?? "—"} MPN
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
  const current = stations.filter(station =>
    !station.stale &&
    station.bacteria != null
  );

  if (!current.length) {
    return {
      status: "⚪",
      detail: "Older samples",
    };
  }

  const counts = current.map(station => station.bacteria);
  const failing = current.some(
    station => station.status === "🔴"
  );

  return {
    status: failing ? "🔴" : "🟢",
    detail: `${Math.min(...counts)}–${Math.max(...counts)} MPN`,
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


function formatDate(value) {
  const date = new Date(value);

  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}


function formatTime(value) {
  const date = new Date(value);

  return date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}


function formatEventWindow(startValue, endValue) {
  const start = new Date(startValue);
  const end = new Date(endValue);

  const date = start.toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
  });

  const startTime = start.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });

  const endTime = end.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });

  return `${date} · ${startTime}–${endTime}`;
}


function formatUpdatedTime(value) {
  const date = new Date(value);

  return date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
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
