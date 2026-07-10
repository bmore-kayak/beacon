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
        ${condition.direction_deg != null ? windArrow(condition.direction_deg) : ""}
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

  content += renderSource(condition.source);

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
  return `
    <div class="stations">
      ${stations.map(station => `
        <div class="station">
          <span>${station.site}</span>
          <span>
            ${station.status}
            ${station.bacteria ?? "—"} MPN
          </span>
        </div>
      `).join("")}
    </div>
  `;
}


function renderSource(source) {
  if (!source) {
    return "";
  }

  return `
    <div class="detail-footer">
      ${source.location ? `<div>${source.location}</div>` : ""}
      ${source.provider ? `<div>${source.provider}</div>` : ""}
      ${source.updated
        ? `<div>Updated ${formatDate(source.updated)}</div>`
        : ""}
    </div>
  `;
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
