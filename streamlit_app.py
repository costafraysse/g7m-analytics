"""
Enedis Grid Analysis Dashboard
Visualizes renewable energy project queue data from Enedis.
"""

import streamlit as st
import pandas as pd
import requests
import hmac
from datetime import datetime, timezone
import plotly.graph_objects as go


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
        margin-bottom: 0.5rem !important;
    }

    h2 {
        font-weight: 600 !important;
        color: #1d1d1f !important;
        margin-top: 3rem !important;
        margin-bottom: 1rem !important;
    }

    h3 {
        font-weight: 500 !important;
        color: #6e6e73 !important;
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

    /* Remove excessive padding */
    .block-container {
        padding-top: 3rem !important;
        padding-bottom: 3rem !important;
        max-width: 1200px !important;
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
    st.markdown("### Authentication Required")
    st.text_input(
        "Enter password to access the dashboard",
        type="password",
        on_change=password_entered,
        key="password"
    )

    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("Incorrect password. Please try again.")

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


def plot_stacked_bar(df, title, emoji):
    """Create interactive stacked bar chart with Plotly."""
    if df.empty:
        return None, 0

    # Calculate totals for each quarter
    totals = df.sum(axis=1).values

    # Create Plotly figure
    fig = go.Figure()

    # Add a bar trace for each category (only if it has non-zero data)
    for cat in CATEGORY_ORDER:
        if cat in df.columns and df[cat].sum() > 0:  # Only show if there's actual data
            fig.add_trace(go.Bar(
                name=cat,
                x=df.index,
                y=df[cat],
                marker_color=COLORS.get(cat, '#CCC'),
                hovertemplate='<b>%{x}</b><br>' + cat + ': %{y:.2f} GW<extra></extra>'
            ))

    # Add text annotations on top of bars showing totals
    for i, (quarter, total) in enumerate(zip(df.index, totals)):
        fig.add_annotation(
            x=quarter,
            y=total,
            text=f'{total:.1f}',
            showarrow=False,
            font=dict(size=11, color='#1d1d1f', family='SF Pro Display, -apple-system, sans-serif', weight=600),
            yshift=10
        )

    # Update layout - clean, Apple-like design
    fig.update_layout(
        barmode='stack',
        title=None,  # Remove chart title, use section headers instead
        xaxis=dict(
            title=None,
            tickangle=-45,
            showgrid=False,
            showline=False,
            tickfont=dict(size=12, color='#6e6e73', family='SF Pro Display, -apple-system, sans-serif')
        ),
        yaxis=dict(
            title='Puissance (GW)',
            gridcolor='#e5e5e5',
            showline=False,
            tickfont=dict(size=12, color='#6e6e73', family='SF Pro Display, -apple-system, sans-serif'),
            titlefont=dict(size=13, color='#6e6e73', family='SF Pro Display, -apple-system, sans-serif')
        ),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=-0.3,
            xanchor='center',
            x=0.5,
            bgcolor='rgba(255,255,255,0)',
            bordercolor='rgba(0,0,0,0)',
            font=dict(size=11, color='#6e6e73', family='SF Pro Display, -apple-system, sans-serif')
        ),
        height=500,
        hovermode='x unified',
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(t=20, r=20, b=140, l=60),
        font=dict(family='SF Pro Display, -apple-system, sans-serif')
    )

    # Calculate total for last quarter
    total = totals[-1] if len(totals) > 0 else 0

    return fig, total


# ============================================================================
# MAIN APP
# ============================================================================

# Load data
data = load_data()

# Header
st.title("Enedis Grid Analysis")
st.markdown("### Renewable energy projects awaiting connection")

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
    status_text = "Recent data"
elif days_since_source <= 45:
    status_text = "Up to date"
elif days_since_source <= 90:
    status_text = "Potentially outdated"
else:
    status_text = "Outdated (>3 months)"

with col1:
    st.metric(
        "Data Status",
        status_text,
        delta=None
    )
    st.caption(f"Last Enedis update: {source_last_update.strftime('%B %d, %Y')}")

with col2:
    st.metric(
        "Last Collection",
        f"{days_since_generated} day{'s' if days_since_generated != 1 else ''} ago",
        delta=None
    )
    st.caption(f"{generated_at.strftime('%B %d, %Y at %H:%M')} UTC")

with col3:
    st.metric(
        "Records",
        f"{data['metadata']['renewable_records']:,}",
        delta=None
    )
    st.caption(f"Out of {data['metadata']['total_records']:,} total")

st.markdown("---")

# Photovoltaic section
st.markdown("## Solar")
st.markdown("Quarterly cumulative queue")

df_pv = create_dataframe_from_data(data['data']['photovoltaic'])
if not df_pv.empty:
    fig_pv, total_pv = plot_stacked_bar(
        df_pv,
        "Solar",
        ""
    )
    st.plotly_chart(fig_pv, use_container_width=True)
    st.info(f"**Latest quarter:** {total_pv:.2f} GW in queue")
else:
    st.warning("No solar data available")

st.markdown("---")

# Wind section
st.markdown("## Wind")
st.markdown("Quarterly cumulative queue")

df_wind = create_dataframe_from_data(data['data']['wind'])
if not df_wind.empty:
    fig_wind, total_wind = plot_stacked_bar(
        df_wind,
        "Wind",
        ""
    )
    st.plotly_chart(fig_wind, use_container_width=True)
    st.info(f"**Latest quarter:** {total_wind:.2f} GW in queue")
else:
    st.warning("No wind data available")

# Combined total
if not df_pv.empty and not df_wind.empty:
    st.markdown("---")
    st.markdown(f"### Combined Total: **{total_pv + total_wind:.2f} GW**")

# Footer
st.markdown("---")
st.caption(f"Source: [Enedis Open Data]({data['metadata']['api_url']})")
st.caption("Data processed automatically every week")
