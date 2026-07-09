async function main() {
  const response = await fetch("data/latest.json");
  const data = await response.json();

  document.title = `Beacon • ${data.location}`;

  document.getElementById("overall").textContent =
    `${data.overall.status} ${data.overall.label}`;

  document.getElementById("note").textContent = data.note;
  document.getElementById("updated").textContent =
    `Last updated ${data.updated}`;

  const tbody = document.getElementById("conditions");
  tbody.innerHTML = "";

  for (const condition of Object.values(data.conditions)) {
    const row = document.createElement("tr");

    row.innerHTML = `
      <td>${condition.icon} ${condition.label}</td>
      <td>${condition.status}</td>
      <td>${condition.detail}</td>
    `;

    tbody.appendChild(row);
  }
}

main();
