// public/main.js

// Firebase Configuration
const firebaseConfig = {
    apiKey: "AIzaSyBBK5PFeHWTblD81Uz56MO8kFp4m_8_ZZQ",
    authDomain: "energymonitoritalia.firebaseapp.com",
    projectId: "energymonitoritalia",
    storageBucket: "energymonitoritalia.appspot.com",
    messagingSenderId: "35063954482",
    appId: "1:35063954482:web:c1fdfa3015bc340c70102b"
};

// Initialize Firebase
firebase.initializeApp(firebaseConfig);
const db = firebase.firestore();

document.addEventListener("DOMContentLoaded", async () => {
    try {
        const simDoc = await db.collection('simulation_results').doc('latest_italy').get();
        if (simDoc.exists) {
            const data = simDoc.data();
            const records = data.records || {}; // Handle case where records might be missing
            document.getElementById('analysis-date').textContent = records.data_analisi || 'N/A';
            document.getElementById('kpi-annual-saving').textContent = `€ ${(records.risparmio_annuale_italia_eur / 1e9).toFixed(2)}`;
            document.getElementById('kpi-family-saving').textContent = `€ ${records.risparmio_annuale_famiglia_eur.toFixed(2)}`;
            document.getElementById('kpi-percentage-saving').textContent = `${records.risparmio_percentuale.toFixed(2)} %`;
            document.getElementById('summary-demand').textContent = Math.round(records.fabbisogno_mwh).toLocaleString('it-IT');
            document.getElementById('summary-actual-cost').textContent = (records.costo_attuale_eur / 1e6).toFixed(2);
            document.getElementById('summary-sim-cost').textContent = (records.costo_simulato_eur / 1e6).toFixed(2);
            document.getElementById('summary-pun-used').textContent = records.pun_usato_eur_mwh.toFixed(2);

        } else {
            console.error("Simulation document not found!");
        }

        const dataDate = getFirestoreDate(2);
        
        const countries = ['italy', 'france', 'spain'];
        for (const country of countries) {
            const doc = await db.collection(`daily_generation_${country}`).doc(dataDate).get();
            if (doc.exists) {
                createAsciiChart(doc.data().records, `${country}-chart-container`);
            }
        }

    } catch (error) {
        console.error("Error loading data from Firestore:", error);
    }
});

function createAsciiChart(records, containerId) {
    const psrTypeMap = {
    'B01': 'Biomass',
    'B02': 'Lignite',
    'B03': 'Coal-derived Gas',
    'B04': 'Fossil Gas',
    'B05': 'Hard Coal',
    'B06': 'Fossil Oil',
    'B07': 'Peat',
    'B08': 'Oil Shale',
    'B09': 'Geothermal',
    'B10': 'Hydro Pumped Storage',
    'B11': 'Hydro Run-of-river',
    'B12': 'Hydro Water Reservoir',
    'B13': 'Marine (wave, tidal)',
    'B14': 'Nuclear',
    'B15': 'Other Renewable',
    'B16': 'Solar',
    'B17': 'Waste',
    'B18': 'Wind Offshore',
    'B19': 'Wind Onshore',
    'B20': 'Other',
    // Energy Storage Codes
    'B25': 'Battery storage',
    'B26': 'Compressed air energy storage',
    'B27': 'Power-to-Gas'
};
    const colorMap = { 'Nuclear': '#9966FF', 'Solar': '#FFCE56', 'Fossil Gas': '#FDB45C', 'Hydro Water Reservoir': '#36A2EB', 'Hydro Run-of-river': '#4BC0C0', 'Wind Onshore': '#A4D9A0', 'Biomass': '#46BFBD', 'Fossil Hard coal': '#949FB1' };

    const container = document.getElementById(containerId);
    if (!container || !records) return;

    const energyTotals = records.reduce((acc, rec) => {
        const sourceName = psrTypeMap[rec.psrType] || rec.psrType;
        acc[sourceName] = (acc[sourceName] || 0) + rec.quantity_MW;
        return acc;
    }, {});
    
    const sortedEnergy = Object.entries(energyTotals).sort(([,a],[,b]) => b-a);
    const totalProduction = sortedEnergy.reduce((sum, [, val]) => sum + val, 0);

    const isMobile = window.innerWidth < 768;
    const itemsToShow = isMobile ? sortedEnergy.slice(0, 5) : sortedEnergy;

    itemsToShow.forEach(([sourceName, totalMW]) => {
        const percentage = (totalProduction > 0) ? (totalMW / totalProduction) * 100 : 0;
        const barLength = Math.round(percentage / 1.5);
        const bar = '█'.repeat(barLength);
        const color = colorMap[sourceName] || '#00ff00';

        const rowHtml = `<div class="ascii-row" title="Click for details"><span class="ascii-label" style="color: ${color};">${sourceName}</span><span class="ascii-bar">${bar}</span><span class="ascii-percentage">(${percentage.toFixed(1)}%)</span></div><div class="ascii-details"> -Total Production: ${Math.round(totalMW).toLocaleString('en-US')} MWh</div>`;
        container.insertAdjacentHTML('beforeend', rowHtml);
    });

    container.querySelectorAll('.ascii-row').forEach(row => {
        row.addEventListener('click', () => {
            const details = row.nextElementSibling;
            details.style.display = details.style.display === 'block' ? 'none' : 'block';
        });
    });
}

function getFirestoreDate(daysAgo) {
    const d = new Date();
    d.setDate(d.getDate() - daysAgo);
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}