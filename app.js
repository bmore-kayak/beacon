async function main() {
  const response = await fetch("data/latest.json");
  const data = await response.json();

  document.title = `Beacon • ${data.location}`;

  document.getElementById("overall").textContent =
    `${data.overall.status} ${data.overall.label}`;

  document.getElementById("note").textContent = data.note;

  document.getElementById("updated").textContent =
    `Last updated ${data.updated}`;

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

      <span class="condition-status">
        ${condition.status}
      </span>

      <span class="condition-detail">
        ${key === "wind" ? windArrow(condition.direction_deg) : ""}
        ${condition.detail}
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

  if (key === "bacteria") {
    content += renderStations(condition.stations);
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
      ${Object.entries(regions).map(([region, regionStations]) => `
        <section class="station-region">
          <div class="station-region-label">${region}</div>

          ${regionStations.map(station => `
            <div class="station">
              <div class="station-info">
                <div class="station-name">${station.site}</div>
            
                <div class="station-date">
                  ${station.date
                    ? `Sampled ${formatSampleDate(station.date)}`
                    : "Sample date unavailable"}
                </div>
              </div>
            
              <div class="station-reading">
                ${station.status} ${station.bacteria ?? "—"} MPN
              </div>
            </div>
          `).join("")}
        </section>
      `).join("")}
    </div>
  `;
}


function renderSource(key, source) {
  if (!source) {
    return "";
  }

  const providers = source.provider
    ? source.provider.split(" · ")
    : [];

  return `
    <div class="detail-footer">
      ${source.location ? `<div>${source.location}</div>` : ""}

      ${providers.map(provider => `
        <div>${provider}</div>
      `).join("")}

      ${source.updated
        ? `<div>${key === "bacteria" ? "Latest sample" : "Updated"} ${formatDate(source.updated)}</div>`
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


main();
