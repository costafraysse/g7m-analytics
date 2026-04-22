"""
Enedis Grid Analysis Dashboard
Visualizes renewable energy project queue data from Enedis.
"""

import streamlit as st
import pandas as pd
import requests
import hmac
from datetime import datetime, timezone
import altair as alt


# Page configuration
st.set_page_config(
    page_title="Enedis Grid Analysis",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for professional Apple-like design
st.markdown("""
<style>
    /* Main content */
    .main {
        background-color: #fafafa;
    }

    /* Headers */
    h1 {
        font-weight: 600 !important;
        letter-spacing: -0.5px !important;
        color: #1d1d1f !important;
        margin-bottom: 0.25rem !important;
        margin-top: 0 !important;
        padding-top: 0 !important;
    }

    h2 {
        font-weight: 600 !important;
        color: #1d1d1f !important;
        margin-top: 1.5rem !important;
        margin-bottom: 0.5rem !important;
    }

    h3 {
        font-weight: 500 !important;
        color: #6e6e73 !important;
        margin-top: 0.25rem !important;
        margin-bottom: 0.5rem !important;
    }

    /* Metrics */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 600 !important;
        color: #1d1d1f !important;
    }

    [data-testid="stMetricLabel"] {
        font-size: 0.9rem !important;
        font-weight: 500 !important;
        color: #6e6e73 !important;
    }

    /* Compact layout */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
        max-width: 1200px !important;
    }

    /* Reduce spacing between elements */
    .stMarkdown {
        margin-bottom: 0.5rem !important;
    }

    /* Compact metrics */
    [data-testid="stMetric"] {
        padding: 0.5rem 0 !important;
    }

    /* Reduce horizontal rule spacing */
    hr {
        margin: 1rem 0 !important;
    }

    /* Info boxes */
    .stAlert {
        border-radius: 12px !important;
        border: none !important;
        background-color: #f5f5f7 !important;
        padding: 1rem 1.5rem !important;
    }

    /* Password input */
    input {
        border-radius: 8px !important;
        border: 1px solid #d2d2d7 !important;
    }

    input:focus {
        border-color: #0071e3 !important;
        box-shadow: 0 0 0 4px rgba(0, 113, 227, 0.1) !important;
    }
</style>
""", unsafe_allow_html=True)


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
    st.markdown("### Authentification Requise")
    st.text_input(
        "Entrez le mot de passe pour accéder au tableau de bord",
        type="password",
        on_change=password_entered,
        key="password"
    )

    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("Mot de passe incorrect. Veuillez réessayer.")

    return False


# Check authentication
if not check_password():
    st.stop()


# ============================================================================
# DATA LOADING
# ============================================================================

@st.cache_data(ttl=86400)  # Cache for 24 hours
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
    'Résidentiel (< 36 kW)': '#0071e3',
    'Moyenne toiture (36-100 kW)': '#147ce5',
    'Grande toiture (100-500 kW)': '#2997ff',
    'Très grande toiture / Petit sol (500 kW-1 MW)': '#64aaff',
    'Sols, toitures, ombrières etc (1-17 MW)': '#8fc1ff',
    'Autoconsommation sans injection (toutes puissances)': '#b4d5ff'
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


def plot_stacked_bar(df, show_legend=True):
    """Create interactive stacked bar chart with Altair."""
    if df.empty:
        return None, 0

    # Calculate totals for each quarter
    totals = df.sum(axis=1)

    # Convert to long format for Altair (only include categories with data)
    df_long = df.reset_index().melt(
        id_vars='quarter',
        var_name='Catégorie',
        value_name='Puissance'
    )

    # Filter out categories with zero data
    df_long = df_long[df_long.groupby('Catégorie')['Puissance'].transform('sum') > 0]

    # Create totals dataframe for labels
    df_totals = pd.DataFrame({
        'quarter': totals.index,
        'total': totals.values
    })

    # Define color scale
    color_scale = alt.Scale(
        domain=list(COLORS.keys()),
        range=list(COLORS.values())
    )

    # Create stacked bar chart
    bars = alt.Chart(df_long).mark_bar().encode(
        x=alt.X('quarter:N',
                title=None,
                axis=alt.Axis(labelAngle=-45, labelColor='#6e6e73')),
        y=alt.Y('Puissance:Q',
                title='Puissance (GW)',
                axis=alt.Axis(gridColor='#e5e5e5', labelColor='#6e6e73', titleColor='#6e6e73')),
        color=alt.Color('Catégorie:N',
                       scale=color_scale,
                       legend=alt.Legend(orient='bottom', titleColor='#6e6e73', labelColor='#6e6e73') if show_legend else None),
        tooltip=[
            alt.Tooltip('quarter:N', title='Trimestre'),
            alt.Tooltip('Catégorie:N', title='Catégorie'),
            alt.Tooltip('Puissance:Q', title='Puissance (GW)', format='.2f')
        ]
    )

    # Add text labels on top showing totals
    text = alt.Chart(df_totals).mark_text(
        align='center',
        baseline='bottom',
        dy=-5,
        fontSize=11,
        color='#1d1d1f',
        fontWeight=600
    ).encode(
        x=alt.X('quarter:N'),
        y=alt.Y('total:Q'),
        text=alt.Text('total:Q', format='.1f')
    )

    # Combine chart
    chart = (bars + text).properties(
        height=400
    ).configure_view(
        strokeWidth=0
    ).configure_axis(
        grid=True,
        gridOpacity=0.3
    )

    # Calculate total for last quarter
    total = totals.iloc[-1] if len(totals) > 0 else 0

    return chart, total


# ============================================================================
# MAIN APP
# ============================================================================

# Load data
data = load_data()

# Header
st.title("Analyse de la File d'Attente Enedis")
st.markdown("Projets d'énergies renouvelables en attente de raccordement")

# Data freshness indicator
st.markdown("")
col1, col2, col3 = st.columns(3)

source_last_update = datetime.fromisoformat(data['source_last_update'].replace('Z', '+00:00'))
generated_at = datetime.fromisoformat(data['generated_at'].replace('Z', '+00:00'))
now = datetime.now(timezone.utc)

days_since_source = (now - source_last_update).days
days_since_generated = (now - generated_at).days

# Source data freshness
if days_since_source <= 7:
    status_text = "Données récentes"
elif days_since_source <= 45:
    status_text = "Données à jour"
elif days_since_source <= 90:
    status_text = "Potentiellement obsolètes"
else:
    status_text = "Données anciennes (>3 mois)"

with col1:
    st.metric(
        "Statut des Données",
        status_text,
        delta=None
    )
    st.caption(f"Dernière mise à jour Enedis : {source_last_update.strftime('%d/%m/%Y')}")

with col2:
    st.metric(
        "Dernière Collecte",
        f"Il y a {days_since_generated} jour{'s' if days_since_generated > 1 else ''}",
        delta=None
    )
    st.caption(f"{generated_at.strftime('%d/%m/%Y à %H:%M')} UTC")

with col3:
    st.metric(
        "Enregistrements",
        f"{data['metadata']['renewable_records']:,}",
        delta=None
    )
    st.caption(f"Sur {data['metadata']['total_records']:,} total")

# Photovoltaic section
st.markdown("## Photovoltaïque")

df_pv = create_dataframe_from_data(data['data']['photovoltaic'])
if not df_pv.empty:
    chart_pv, total_pv = plot_stacked_bar(df_pv)
    st.altair_chart(chart_pv, use_container_width=True)
    st.info(f"**Dernier trimestre :** {total_pv:.2f} GW en file d'attente")
else:
    st.warning("Aucune donnée photovoltaïque disponible")

# Wind section
st.markdown("## Éolien")

df_wind = create_dataframe_from_data(data['data']['wind'])
if not df_wind.empty:
    chart_wind, total_wind = plot_stacked_bar(df_wind, show_legend=False)
    st.altair_chart(chart_wind, use_container_width=True)
    st.info(f"**Dernier trimestre :** {total_wind:.2f} GW en file d'attente")
else:
    st.warning("Aucune donnée éolienne disponible")

# Combined total
if not df_pv.empty and not df_wind.empty:
    st.markdown(f"### Total Combiné : **{total_pv + total_wind:.2f} GW**")

# Footer
st.markdown("")
st.caption(f"Source : [Enedis Open Data]({data['metadata']['api_url']}) • Données traitées automatiquement chaque semaine")
