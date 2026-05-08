// Constants for Motor Full-Load Current (Source: t9 (1).jpg)
//page na toh for functions// 
const motorTable = {
    "0.166": { 115: 4.4, 200: 2.5, 208: 2.4, 230: 2.2 },
    "0.25":  { 115: 5.8, 200: 3.3, 208: 3.2, 230: 2.9 },
    "0.33":  { 115: 7.2, 200: 4.1, 208: 4.0, 230: 3.6 },
    "0.5":   { 115: 9.8, 200: 5.6, 208: 5.4, 230: 4.9 },
    "0.75":  { 115: 13.8, 200: 7.9, 208: 7.6, 230: 6.9 },
    "1":     { 115: 16, 200: 9.2, 208: 8.8, 230: 8 },
    "1.5":   { 115: 20, 200: 11.5, 208: 11, 230: 10 },
    "2":     { 115: 24, 200: 13.8, 208: 13.2, 230: 12 },
    "3":     { 115: 34, 200: 19.6, 208: 18.7, 230: 17 },
    "5":     { 115: 56, 200: 32.2, 208: 30.8, 230: 28 },
    "7.5":   { 115: 80, 200: 46, 208: 44, 230: 40 },
    "10":    { 115: 100, 200: 57.5, 208: 55, 230: 50 }
};
// 
// Cooking Appliance Demand Factors (Source: t8 (1).jpg)
const tableColA = [0, 8, 11, 14, 17, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40];
const tableColB = [0, 80, 75, 70, 66, 62, 59, 56, 53, 51, 49, 47, 45, 43, 41, 40, 39, 38, 37, 36, 35, 34, 33, 32, 31, 30];
const tableColC = [0, 80, 65, 55, 50, 45, 43, 40, 36, 35, 34, 32, 32, 32, 32, 32, 28, 28, 28, 28, 28, 26, 26, 26, 26, 26];

/**
 * Navigation & UI Functions
 */
function toggleMode() {
    const body = document.body;
    const current = body.getAttribute('data-theme');
    body.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
}

function startApp() {
    document.getElementById('start-screen').style.display = 'none';
    document.getElementById('calc-app').style.display = 'block';
    document.getElementById('sticky-total').style.display = 'flex';
    document.getElementById('nav-return').style.display = 'flex';
    document.getElementById('nav-admin').style.display = 'none';
}

function goHome() {
    document.getElementById('start-screen').style.display = 'block';
    document.getElementById('calc-app').style.display = 'none';
    document.getElementById('sticky-total').style.display = 'none';
    document.getElementById('nav-return').style.display = 'none';
    document.getElementById('nav-admin').style.display = 'flex';
    document.getElementById('admin-panel').style.display = 'none';
}

function showAdmin() {
    document.getElementById('start-screen').style.display = 'none';
    document.getElementById('admin-panel').style.display = 'block';
    document.getElementById('nav-return').style.display = 'flex';
}

/**
 * Reference Table Logic (Displays data from uploaded images)
 */
function switchTable() {
    const val = document.getElementById('table-selector').value;
    const display = document.getElementById('table-display');
    const head = document.getElementById('ref-thead');
    const body = document.getElementById('ref-tbody');
    
    if(val === "none") {
        display.style.display = "none";
        return;
    }

    display.style.display = "block";
    body.innerHTML = "";

    if(val === "motor") {
        head.innerHTML = "<tr><th>HP</th><th>115V</th><th>200V</th><th>208V</th><th>230V</th></tr>";
        for(let hp in motorTable) {
            body.innerHTML += `<tr><td>${hp}</td><td>${motorTable[hp][115]}</td><td>${motorTable[hp][200]}</td><td>${motorTable[hp][208]}</td><td>${motorTable[hp][230]}</td></tr>`;
        }
    } else if(val === "lighting") {
        head.innerHTML = "<tr><th>Occupancy</th><th>First Limit</th><th>Factor</th></tr>";
        body.innerHTML = `<tr><td>Dwelling</td><td>3,000 VA</td><td>100% / 35% / 25%</td></tr>
                          <tr><td>Hospitals</td><td>50,000 VA</td><td>40% / 20%</td></tr>
                          <tr><td>Hotels</td><td>20,000 VA</td><td>50% / 40% / 30%</td></tr>
                          <tr><td>Warehouses</td><td>12,500 VA</td><td>100% / 50%</td></tr>`;
    } else if(val === "dryer") {
        head.innerHTML = "<tr><th>Qty</th><th>Factor (%)</th></tr>";
        body.innerHTML += `<tr><td>1-4</td><td>100%</td></tr><tr><td>5</td><td>80%</td></tr><tr><td>10</td><td>50%</td></tr>`;
    } else if(val === "cooking") {
        head.innerHTML = "<tr><th>Qty</th><th>Col A (kW)</th><th>Col B (%)</th><th>Col C (%)</th></tr>";
        for(let i=1; i<=10; i++) {
            body.innerHTML += `<tr><td>${i}</td><td>${tableColA[i]}</td><td>${tableColB[i]}%</td><td>${tableColC[i]}%</td></tr>`;
        }
    }
}

/**
 * Core Calculation Logic
 */
function liveCalc() {
    const lighting = parseFloat(document.getElementById('in-lighting').value) || 0;
    const qtyFixed = Math.min(25, parseInt(document.getElementById('qty-fixed').value) || 0);
    const fixedVA = parseFloat(document.getElementById('in-fixed').value) || 0;
    const qtyDryer = parseInt(document.getElementById('qty-dryer').value) || 0;
    const dryerVA = parseFloat(document.getElementById('in-dryer').value) || 0;
    
    const hp = document.getElementById('motor-hp').value;
    const volts = document.getElementById('motor-volts').value;

    // 1. Lighting Calculation (General Dwelling)
    let dLighting = lighting > 3000 ? 3000 + (lighting - 3000) * 0.35 : lighting;
    
    // 2. Cooking Appliances (Source: t8 (1).jpg logic)
    let dFixed = 0;
    let kw = fixedVA / 1000;
    if (qtyFixed > 0 && kw > 0) {
        if (kw < 3.5) dFixed = (fixedVA * qtyFixed) * (tableColB[qtyFixed] / 100);
        else if (kw <= 8.75) dFixed = (fixedVA * qtyFixed) * (tableColC[qtyFixed] / 100);
        else dFixed = tableColA[qtyFixed] * 1000;
    }

    // 3. Clothes Dryers (Min 5000 VA as per PEC)
    let dDryer = qtyDryer > 0 ? (Math.max(5000, dryerVA) * qtyDryer) : 0;

    // 4. Largest Motor (125% of FLC)
    let dMotor = 0;
    if(hp !== "0") {
        const amps = motorTable[hp][volts];
        dMotor = (amps * volts) * 1.25;
    }

    // Update Display
    document.getElementById('res-lighting').innerText = `Demand: ${Math.round(dLighting).toLocaleString()} VA`;
    document.getElementById('res-fixed').innerText = `Demand: ${Math.round(dFixed).toLocaleString()} VA`;
    document.getElementById('res-dryer').innerText = `Demand: ${Math.round(dDryer).toLocaleString()} VA`;
    document.getElementById('res-motor').innerText = `Demand: ${Math.round(dMotor).toLocaleString()} VA`;

    const total = dLighting + dFixed + dDryer + dMotor;
    document.getElementById('grand-total').innerText = total.toLocaleString(undefined, {minimumFractionDigits: 2});
}
