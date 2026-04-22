"""
Enedis Grid Analysis Dashboard
Visualizes renewable energy project queue data from Enedis.
"""

import streamlit as st
import pandas as pd
import requests
import hmac
from datetime import datetime, timezone


# Page configuration
st.set_page_config(
    page_title="Enedis Grid Analysis",
    page_icon="⚡",
    layout="wide"
)


# ============================================================================
# AUTHENTICATION
# ============================================================================

def check_password():
    """Returns True if user entered correct password."""

    def password_entered():
        """Check password and update session state."""
        if hmac.compare_digest(st.session_state["password"], st.secrets["password"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    # Return True if password is correct
    if st.session_state.get("password_correct", False):
        return True

    # Show password input
    st.markdown("### 🔒 Authentication Required")
    st.text_input(
        "Enter password to access the dashboard",
        type="password",
        on_change=password_entered,
        key="password"
    )

    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("❌ Incorrect password. Please try again.")

    return False


# Check authentication
if not check_password():
    st.stop()


# ============================================================================
# DATA LOADING
# ============================================================================

@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_data():
    """Load data from GitHub Gist or local file."""
    try:
        gist_url = st.secrets["gist_url"]

        # Support local file loading for testing
        if gist_url.startswith("file://"):
            import json
            file_path = gist_url.replace("file://", "")
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            response = requests.get(gist_url, timeout=10)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"❌ Failed to load data: {str(e)}")
        st.stop()


# ============================================================================
# CONFIGURATION
# ============================================================================

COLORS = {
    'Résidentiel (< 36 kW)': '#8B7355',
    'Moyenne toiture (36-100 kW)': '#D2B48C',
    'Grande toiture (100-500 kW)': '#E8D5A0',
    'Très grande toiture / Petit sol (500 kW-1 MW)': '#F4E5B8',
    'Sols, toitures, ombrières etc (1-17 MW)': '#FFF4D0',
    'Autoconsommation sans injection (toutes puissances)': '#FFC857'
}

CATEGORY_ORDER = [
    'Résidentiel (< 36 kW)',
    'Moyenne toiture (36-100 kW)',
    'Grande toiture (100-500 kW)',
    'Très grande toiture / Petit sol (500 kW-1 MW)',
    'Sols, toitures, ombrières etc (1-17 MW)',
    'Autoconsommation sans injection (toutes puissances)'
]


# ============================================================================
# VISUALIZATION FUNCTIONS
# ============================================================================

def create_dataframe_from_data(data_dict):
    """Convert data dict to DataFrame for plotting."""
    if not data_dict:
        return pd.DataFrame()

    records = []
    for quarter_label, quarter_data in data_dict.items():
        row = {'quarter': quarter_label}
        row.update(quarter_data['categories'])
        records.append(row)

    df = pd.DataFrame(records)
    df = df.set_index('quarter')

    # Ensure all categories are present
    for cat in CATEGORY_ORDER:
        if cat not in df.columns:
            df[cat] = 0.0

    # Reorder columns
    df = df[[col for col in CATEGORY_ORDER if col in df.columns]]

    return df


def plot_stacked_bar(df, title, emoji):
    """Create stacked bar chart using Streamlit's native charting."""
    if df.empty:
        return None, 0

    # Calculate total for last quarter
    total = df.iloc[-1].sum() if len(df) > 0 else 0

    return df, total


# ============================================================================
# MAIN APP
# ============================================================================

# Load data
data = load_data()

# Header
st.title("⚡ Analyse de la File d'Attente Enedis")
st.markdown("### Projets d'énergies renouvelables en attente de raccordement")

# Data freshness indicator
st.markdown("---")
col1, col2, col3 = st.columns(3)

source_last_update = datetime.fromisoformat(data['source_last_update'].replace('Z', '+00:00'))
generated_at = datetime.fromisoformat(data['generated_at'].replace('Z', '+00:00'))
now = datetime.now(timezone.utc)

days_since_source = (now - source_last_update).days
days_since_generated = (now - generated_at).days

# Source data freshness
if days_since_source <= 7:
    status_color = "🟢"
    status_text = "Données récentes"
elif days_since_source <= 45:
    status_color = "🟢"
    status_text = "Données à jour"
elif days_since_source <= 90:
    status_color = "🟡"
    status_text = "Données potentiellement obsolètes"
else:
    status_color = "🔴"
    status_text = "Données anciennes (> 3 mois)"

with col1:
    st.metric(
        "Statut des données",
        status_text,
        delta=None
    )
    st.caption(f"{status_color} Dernière mise à jour Enedis: {source_last_update.strftime('%d/%m/%Y')}")

with col2:
    st.metric(
        "Dernière collecte",
        f"Il y a {days_since_generated} jour{'s' if days_since_generated > 1 else ''}",
        delta=None
    )
    st.caption(f"📥 {generated_at.strftime('%d/%m/%Y à %H:%M')} UTC")

with col3:
    st.metric(
        "Enregistrements",
        f"{data['metadata']['renewable_records']:,}",
        delta=None
    )
    st.caption(f"📊 Sur {data['metadata']['total_records']:,} total")

st.markdown("---")

# Photovoltaic section
st.markdown("## 🌞 Photovoltaïque")
st.markdown("#### Cumul trimestriel des projets en file d'attente")

df_pv = create_dataframe_from_data(data['data']['photovoltaic'])
if not df_pv.empty:
    chart_df, total_pv = plot_stacked_bar(
        df_pv,
        "Photovoltaïque - Cumul trimestriel des projets en file d'attente",
        "🌞"
    )
    st.bar_chart(chart_df, color=list(COLORS.values())[:len(chart_df.columns)], height=500)
    st.info(f"**Dernier trimestre:** {total_pv:.2f} GW en file d'attente")
else:
    st.warning("Aucune donnée photovoltaïque disponible")

st.markdown("---")

# Wind section
st.markdown("## 💨 Éolien")
st.markdown("#### Cumul trimestriel des projets en file d'attente")

df_wind = create_dataframe_from_data(data['data']['wind'])
if not df_wind.empty:
    chart_df, total_wind = plot_stacked_bar(
        df_wind,
        "Éolien - Cumul trimestriel des projets en file d'attente",
        "💨"
    )
    st.bar_chart(chart_df, color=list(COLORS.values())[:len(chart_df.columns)], height=500)
    st.info(f"**Dernier trimestre:** {total_wind:.2f} GW en file d'attente")
else:
    st.warning("Aucune donnée éolienne disponible")

# Combined total
if not df_pv.empty and not df_wind.empty:
    st.markdown("---")
    st.markdown(f"### 📊 Total Combiné: **{total_pv + total_wind:.2f} GW**")

# Footer
st.markdown("---")
st.caption(f"Source: [Enedis Open Data]({data['metadata']['api_url']})")
st.caption("Données traitées automatiquement chaque semaine")
