async function main() {
  const response = await fetch("../data/latest.json");
  const data = await response.json();

  document.title = `Beacon • ${data.location}`;
  document.getElementById("overall").textContent = data.overall;
  document.getElementById("note").textContent = data.note;
  document.getElementById("updated").textContent =
    `Last updated ${data.updated}`;

  const tbody = document.getElementById("conditions");

  for (const [condition, status, detail] of data.conditions) {
    const row = document.createElement("tr");

    row.innerHTML = `
      <td>${condition}</td>
      <td>${status}</td>
      <td>${detail}</td>
    `;

    tbody.appendChild(row);
  }
}

main();
