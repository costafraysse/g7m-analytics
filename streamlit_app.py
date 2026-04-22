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
import folium
from streamlit_folium import st_folium


# Page configuration
st.set_page_config(
    page_title="Plateforme d'analyse",
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
        font-size: 1.75rem !important;
        font-weight: 600 !important;
        letter-spacing: -0.3px !important;
        color: #1d1d1f !important;
        margin-bottom: 0.5rem !important;
        margin-top: 0 !important;
        padding-top: 0 !important;
        line-height: 1.3 !important;
    }

    h2 {
        font-size: 1.5rem !important;
        font-weight: 600 !important;
        color: #1d1d1f !important;
        margin-top: 1.5rem !important;
        margin-bottom: 0.5rem !important;
        line-height: 1.3 !important;
    }

    h3 {
        font-size: 1.1rem !important;
        font-weight: 500 !important;
        color: #6e6e73 !important;
        margin-top: 0.25rem !important;
        margin-bottom: 0.75rem !important;
        line-height: 1.4 !important;
    }

    /* Subtitle paragraph */
    .main p {
        font-size: 0.95rem !important;
        color: #6e6e73 !important;
        margin-bottom: 1.5rem !important;
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
        padding-top: 2.5rem !important;
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

@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_data():
    """Load Enedis data from GitHub Gist or local file."""
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
        st.error(f"❌ Failed to load Enedis data: {str(e)}")
        st.stop()


@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_rte_data():
    """Load RTE CartoStock data from GitHub Gist or local file."""
    try:
        gist_url_rte = st.secrets.get("gist_url_rte")

        if not gist_url_rte:
            return None

        # Support local file loading for testing
        if gist_url_rte.startswith("file://"):
            import json
            file_path = gist_url_rte.replace("file://", "")
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            response = requests.get(gist_url_rte, timeout=10)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.warning(f"⚠️ Could not load RTE data: {str(e)}")
        return None


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


def create_rte_map(snapshot_data, center_lat=46.603354, center_lon=1.888334, zoom_start=6):
    """
    Create a Folium map showing RTE substations for a given snapshot.

    Args:
        snapshot_data: Snapshot dict with 'substations' list
        center_lat: Map center latitude
        center_lon: Map center longitude
        zoom_start: Initial zoom level

    Returns:
        Folium map object
    """
    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_start,
        tiles='OpenStreetMap'
    )

    if not snapshot_data or 'substations' not in snapshot_data:
        return m

    # Color mapping for capacity
    def get_capacity_color(capacity_str):
        """Get marker color based on capacity."""
        if not capacity_str or capacity_str == 'null':
            return 'gray'
        if '< 5' in str(capacity_str):
            return 'orange'
        elif '5-10' in str(capacity_str):
            return 'yellow'
        elif '10-25' in str(capacity_str):
            return 'lightgreen'
        elif '> 25' in str(capacity_str) or '>= 25' in str(capacity_str):
            return 'green'
        else:
            return 'blue'

    # Add markers for each substation
    for feature in snapshot_data['substations']:
        coords = feature.get('geometry', {}).get('coordinates', [])
        props = feature.get('properties', {})

        if len(coords) >= 2:
            lat, lon = coords[1], coords[0]

            capacity = props.get('CapaciteSansContrainte', 'N/A')
            gabarit_capacity = props.get('CapacitePosteGabarit', 'N/A')
            gabarit = props.get('Gabarit', 'Non')
            demand = props.get('DemandeProximite', '0')

            color = get_capacity_color(capacity)

            # Create popup content
            popup_html = f"""
            <div style="font-family: sans-serif; min-width: 200px;">
                <h4 style="margin-bottom: 5px;">{props.get('ADRPoste', 'N/A')}</h4>
                <p style="margin: 2px 0;"><strong>ID:</strong> {props.get('IDRPoste', 'N/A')}</p>
                <p style="margin: 2px 0;"><strong>Commune:</strong> {props.get('NomCommune', 'N/A')}</p>
                <hr style="margin: 5px 0;">
                <p style="margin: 2px 0;"><strong>Capacité sans contrainte:</strong> {capacity}</p>
                <p style="margin: 2px 0;"><strong>Capacité avec gabarit:</strong> {gabarit_capacity or 'N/A'}</p>
                <p style="margin: 2px 0;"><strong>Gabarit:</strong> {gabarit or 'Non'}</p>
                <p style="margin: 2px 0;"><strong>Zone en concurrence:</strong> {'Oui' if demand == '1' else 'Non'}</p>
            </div>
            """

            folium.CircleMarker(
                location=[lat, lon],
                radius=5,
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.7,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=props.get('NomCommune', 'N/A')
            ).add_to(m)

    return m


def create_rte_changes_map(changes_data, snapshot_data, center_lat=46.603354, center_lon=1.888334, zoom_start=6):
    """
    Create a Folium map showing only substations that changed.

    Args:
        changes_data: Changes dict with 'modified', 'added_substations', 'removed_substations'
        snapshot_data: Current snapshot for coordinate lookup
        center_lat: Map center latitude
        center_lon: Map center longitude
        zoom_start: Initial zoom level

    Returns:
        Folium map object
    """
    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_start,
        tiles='OpenStreetMap'
    )

    if not changes_data:
        return m

    # Index current substations by ID for coordinate lookup
    substation_coords = {}
    if snapshot_data and 'substations' in snapshot_data:
        for feature in snapshot_data['substations']:
            coords = feature.get('geometry', {}).get('coordinates', [])
            props = feature.get('properties', {})
            sub_id = props.get('IDRPoste')
            if sub_id and len(coords) >= 2:
                substation_coords[sub_id] = (coords[1], coords[0])  # lat, lon

    # Add modified substations (blue)
    for change in changes_data.get('modified', []):
        sub_id = change.get('IDRPoste')
        if sub_id in substation_coords:
            lat, lon = substation_coords[sub_id]

            changes_list = []
            for field, vals in change.get('changes', {}).items():
                old_val = vals.get('old', 'N/A')
                new_val = vals.get('new', 'N/A')
                if old_val != new_val:
                    changes_list.append(f"<li><strong>{field}:</strong> {old_val} → {new_val}</li>")

            popup_html = f"""
            <div style="font-family: sans-serif; min-width: 250px;">
                <h4 style="margin-bottom: 5px; color: #0071e3;">MODIFIÉ</h4>
                <p style="margin: 2px 0;"><strong>Poste:</strong> {change.get('ADRPoste', 'N/A')}</p>
                <p style="margin: 2px 0;"><strong>Commune:</strong> {change.get('NomCommune', 'N/A')}</p>
                <hr style="margin: 5px 0;">
                <ul style="margin: 5px 0; padding-left: 20px;">
                    {''.join(changes_list)}
                </ul>
            </div>
            """

            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color='blue',
                fill=True,
                fillColor='blue',
                fillOpacity=0.8,
                popup=folium.Popup(popup_html, max_width=350),
                tooltip=f"Modifié: {change.get('NomCommune', 'N/A')}"
            ).add_to(m)

    # Add new substations (green)
    for sub in changes_data.get('added_substations', []):
        sub_id = sub.get('IDRPoste')
        if sub_id in substation_coords:
            lat, lon = substation_coords[sub_id]

            popup_html = f"""
            <div style="font-family: sans-serif; min-width: 200px;">
                <h4 style="margin-bottom: 5px; color: green;">NOUVEAU</h4>
                <p style="margin: 2px 0;"><strong>Poste:</strong> {sub.get('ADRPoste', 'N/A')}</p>
                <p style="margin: 2px 0;"><strong>Commune:</strong> {sub.get('NomCommune', 'N/A')}</p>
                <p style="margin: 2px 0;"><strong>Capacité:</strong> {sub.get('CapaciteSansContrainte', 'N/A')}</p>
            </div>
            """

            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color='green',
                fill=True,
                fillColor='green',
                fillOpacity=0.8,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"Nouveau: {sub.get('NomCommune', 'N/A')}"
            ).add_to(m)

    # Add removed substations (red) - need to get coords from somewhere
    for sub in changes_data.get('removed_substations', []):
        # Note: Removed substations won't be in current snapshot
        # We'd need to look in previous snapshot or store coords in change log
        pass

    return m


# ============================================================================
# MAIN APP
# ============================================================================

# Load data
data = load_data()

# Header
st.title("Plateforme d'analyse")
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
        "Projets Renouvelables",
        f"{data['metadata']['renewable_records']:,}",
        delta=None,
        help="Nombre de projets photovoltaïques et éoliens en file d'attente de raccordement au réseau Enedis"
    )
    st.caption(f"Sur {data['metadata']['total_records']:,} projets au total")

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

st.markdown("---")
st.caption(f"Source : [Enedis Open Data]({data['metadata']['api_url']}) • Données traitées automatiquement chaque semaine")

# ============================================================================
# RTE CARTOSTOCK SECTION
# ============================================================================

st.markdown("")
st.markdown("## CartoStock RTE")
st.markdown("Capacités d'accueil pour le stockage sur le réseau de transport")

# Load RTE data
rte_data = load_rte_data()

if rte_data and rte_data.get('snapshots'):
    # RTE Data freshness
    st.markdown("")
    col1, col2, col3 = st.columns(3)

    generated_at_rte = datetime.fromisoformat(rte_data['generated_at'].replace('Z', '+00:00'))
    days_since_generated_rte = (now - generated_at_rte).days

    with col1:
        st.metric(
            "Dernière Collecte",
            f"Il y a {days_since_generated_rte} jour{'s' if days_since_generated_rte > 1 else ''}",
            delta=None
        )
        st.caption(f"{generated_at_rte.strftime('%d/%m/%Y à %H:%M')} UTC")

    with col2:
        st.metric(
            "Postes Disponibles",
            f"{rte_data['metadata']['latest_substations']:,}",
            delta=None,
            help="Nombre de postes RTE avec capacité d'accueil pour le stockage"
        )
        st.caption(f"{rte_data['metadata']['latest_zones']} zones gabarit")

    with col3:
        st.metric(
            "Historique",
            f"{rte_data['metadata']['total_snapshots']} snapshots",
            delta=None,
            help="Nombre de collectes de données historiques"
        )
        if rte_data.get('change_log') and len(rte_data['change_log']) > 0:
            latest_change = rte_data['change_log'][-1]
            st.caption(f"Dernier: {latest_change['summary']}")

    # Date slider for navigating snapshots
    st.markdown("")
    snapshots = rte_data['snapshots']
    snapshot_dates = [datetime.fromisoformat(s['date'].replace('Z', '+00:00')) for s in snapshots]

    if len(snapshot_dates) > 1:
        selected_idx = st.slider(
            "Sélectionner une date",
            min_value=0,
            max_value=len(snapshots) - 1,
            value=len(snapshots) - 1,
            format=""
        )
        selected_date = snapshot_dates[selected_idx]
        st.caption(f"📅 Snapshot du {selected_date.strftime('%d/%m/%Y à %H:%M')} UTC")
    else:
        selected_idx = 0
        selected_date = snapshot_dates[0] if snapshot_dates else None
        st.info(f"📅 Snapshot unique du {selected_date.strftime('%d/%m/%Y à %H:%M')} UTC")

    selected_snapshot = snapshots[selected_idx]

    # Two columns for the two maps
    st.markdown("")
    col_map1, col_map2 = st.columns(2)

    with col_map1:
        st.markdown("### État des Postes")
        st.caption("Vue d'ensemble de tous les postes et leur capacité disponible")

        # Create and display state map
        state_map = create_rte_map(selected_snapshot)
        st_folium(state_map, width=550, height=500, key=f"state_map_{selected_idx}")

        # Legend
        st.markdown("""
        **Légende:**
        - 🟢 Vert: > 25 MW
        - 🟡 Jaune clair: 10-25 MW
        - 🟡 Jaune: 5-10 MW
        - 🟠 Orange: < 5 MW
        - ⚫ Gris: Aucune capacité
        """)

    with col_map2:
        st.markdown("### Changements")
        st.caption("Modifications par rapport au snapshot précédent")

        # Get changes for selected snapshot
        if selected_idx > 0 and rte_data.get('change_log'):
            selected_changes = rte_data['change_log'][selected_idx]

            if selected_changes.get('added') > 0 or selected_changes.get('removed') > 0 or len(selected_changes.get('modified', [])) > 0:
                # Create and display changes map
                changes_map = create_rte_changes_map(selected_changes, selected_snapshot)
                st_folium(changes_map, width=550, height=500, key=f"changes_map_{selected_idx}")

                # Summary
                st.markdown(f"""
                **Résumé:**
                - ✅ Ajoutés: {selected_changes['added']}
                - ❌ Supprimés: {selected_changes['removed']}
                - 🔄 Modifiés: {len(selected_changes.get('modified', []))}
                """)
            else:
                st.info("Aucun changement détecté pour ce snapshot")
        else:
            st.info("Premier snapshot - aucune comparaison disponible")

        # Legend for changes
        st.markdown("""
        **Légende:**
        - 🔵 Bleu: Modifié
        - 🟢 Vert: Nouveau
        - 🔴 Rouge: Supprimé
        """)

    # Changes table
    if selected_idx > 0 and rte_data.get('change_log'):
        selected_changes = rte_data['change_log'][selected_idx]

        if len(selected_changes.get('modified', [])) > 0:
            st.markdown("")
            st.markdown("### Détails des Modifications")

            changes_list = []
            for change in selected_changes['modified']:
                for field, vals in change.get('changes', {}).items():
                    if vals['old'] != vals['new']:
                        changes_list.append({
                            'Poste': change.get('ADRPoste', 'N/A'),
                            'Commune': change.get('NomCommune', 'N/A'),
                            'Champ': field,
                            'Ancienne Valeur': vals['old'],
                            'Nouvelle Valeur': vals['new']
                        })

            if changes_list:
                df_changes = pd.DataFrame(changes_list)
                st.dataframe(df_changes, use_container_width=True, hide_index=True)

else:
    st.info("Les données RTE CartoStock ne sont pas encore disponibles. Elles seront ajoutées lors de la prochaine collecte automatique.")

# Footer
st.markdown("")
st.caption("Source RTE : [CartoStock](https://cartostock.cloud-rte-france.com/) • Données collectées automatiquement chaque semaine")
