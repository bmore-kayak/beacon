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

function renderCondition(key, condition) {
  const details = document.createElement("details");
  details.className = "condition";

  const expanded = renderExpandedContent(key, condition);

  details.innerHTML = `
    <summary class="condition-row">
      <span class="condition-label">${condition.icon} ${condition.label}</span>
      <span class="condition-status">${condition.status}</span>
      <span class="condition-detail">${condition.detail}</span>
      <span class="condition-chevron" aria-hidden="true">▾</span>
    </summary>

    ${expanded}
  `;

  return details;
}

function renderExpandedContent(key, condition) {
  if (key !== "water_contact") {
    return "";
  }

  const stations = condition.stations || [];
  const source = condition.source || {};

  return `
    <div class="condition-details">
      <div class="stations">
        ${stations.map(station => `
          <div class="station">
            <span>${station.site}</span>
            <span>${station.status} ${station.bacteria ?? "—"} MPN</span>
          </div>
        `).join("")}
      </div>

      <div class="detail-footer">
        <div>${source.provider || "Waterfront Partnership"}</div>
        <div>${formatDate(source.updated)}</div>
      </div>
    </div>
  `;
}

function formatDate(value) {
  if (!value) return "";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return `Updated ${date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })}`;
}

main();
