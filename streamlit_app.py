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
        # Check if password key exists in session state
        if "password" in st.session_state and st.session_state["password"]:
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


def reconstruct_snapshot_from_deltas(base_snapshot, snapshots, target_index):
    """
    Reconstruct full snapshot state from base + deltas up to target index.

    Args:
        base_snapshot: Base snapshot data with 'substations' and 'gabarit_zones'
        snapshots: List of all snapshots (bases and deltas)
        target_index: Index of target snapshot to reconstruct to

    Returns:
        Reconstructed snapshot dict with 'substations' and 'gabarit_zones'
    """
    if not base_snapshot:
        return {'substations': [], 'gabarit_zones': []}

    # Start with base
    current_state = {
        'substations': {
            sub['properties']['IDRPoste']: sub
            for sub in base_snapshot.get('substations', [])
        },
        'gabarit_zones': base_snapshot.get('gabarit_zones', [])
    }

    # Apply snapshots up to target index
    for i, snapshot in enumerate(snapshots):
        if i > target_index:
            break

        if snapshot.get('type') == 'base':
            # Reset to new base
            current_state = {
                'substations': {
                    sub['properties']['IDRPoste']: sub
                    for sub in snapshot['data'].get('substations', [])
                },
                'gabarit_zones': snapshot['data'].get('gabarit_zones', [])
            }
        elif snapshot.get('type') == 'delta':
            # Apply delta changes
            delta = snapshot.get('data', {})

            # Add new substations
            for sub in delta.get('added', []):
                current_state['substations'][sub['properties']['IDRPoste']] = sub

            # Remove substations
            for sub_id in delta.get('removed', []):
                current_state['substations'].pop(sub_id, None)

            # Update modified substations
            for sub_id, sub in delta.get('modified', {}).items():
                current_state['substations'][sub_id] = sub

    return {
        'date': snapshots[target_index].get('date'),
        'substations': list(current_state['substations'].values()),
        'gabarit_zones': current_state['gabarit_zones']
    }


@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_rte_data():
    """Load RTE CartoStock data from GitHub Gist or local file (supports v1.0 and v2.0 formats)."""
    try:
        gist_url_rte = st.secrets.get("gist_url_rte")

        if not gist_url_rte:
            return None

        # Support local file loading for testing
        if gist_url_rte.startswith("file://"):
            import json
            file_path = gist_url_rte.replace("file://", "")
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            response = requests.get(gist_url_rte, timeout=10)
            response.raise_for_status()
            data = response.json()

        # Convert v2.0 format to v1.0 format for backward compatibility
        if data.get('version') == '2.0':
            try:
                # Reconstruct all snapshots from base + deltas
                base_snapshot = data.get('base_snapshot')
                compressed_snapshots = data.get('snapshots', [])

                reconstructed_snapshots = []
                for i in range(len(compressed_snapshots)):
                    reconstructed = reconstruct_snapshot_from_deltas(base_snapshot, compressed_snapshots, i)
                    reconstructed_snapshots.append(reconstructed)

                # Return in v1.0-compatible format
                return {
                    'generated_at': data['generated_at'],
                    'metadata': data['metadata'],
                    'snapshots': reconstructed_snapshots,
                    'change_log': []  # v2.0 doesn't have change_log in same format
                }
            except Exception as e:
                st.warning(f"⚠️ Could not reconstruct v2.0 format: {str(e)}")
                return None

        # Return v1.0 format as-is
        return data

    except Exception as e:
        st.warning(f"⚠️ Could not load RTE data: {str(e)}")
        return None


@st.cache_data(ttl=3600)
def load_capareseau_data():
    """Load Capareseau data from GitHub Gist or local file."""
    try:
        gist_url_capareseau = st.secrets.get("gist_url_capareseau")

        if not gist_url_capareseau:
            return None

        # Support local file loading for testing
        if gist_url_capareseau.startswith("file://"):
            import json
            file_path = gist_url_capareseau.replace("file://", "")
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            response = requests.get(gist_url_capareseau, timeout=10)
            response.raise_for_status()
            data = response.json()

        # Handle v2.0 format with delta compression
        if data.get('version') == '2.0':
            # Reconstruct latest snapshot from base + deltas
            data = reconstruct_capareseau_latest(data)

        return data
    except Exception as e:
        st.warning(f"⚠️ Could not load Capareseau data: {str(e)}")
        return None


def reconstruct_capareseau_latest(data):
    """
    Reconstruct the latest full snapshot from v2.0 delta-encoded data.

    Args:
        data: v2.0 format data with base_snapshot and snapshots

    Returns:
        Data in old format compatible with UI (with latest_snapshot having substations field)
    """
    base_snapshot = data.get('base_snapshot', {})
    snapshots = data.get('snapshots', [])

    if not base_snapshot or not snapshots:
        return data

    # Start with base snapshot substations
    current_state = {sub['code']: sub for sub in base_snapshot.get('substations', [])}

    # Apply each snapshot in order
    for snapshot in snapshots:
        snapshot_type = snapshot.get('type')

        if snapshot_type == 'base':
            # Reset to new base
            current_state = {sub['code']: sub for sub in snapshot.get('data', {}).get('substations', [])}

        elif snapshot_type == 'delta':
            delta = snapshot.get('data', {})

            # Add new substations
            for sub in delta.get('added', []):
                current_state[sub['code']] = sub

            # Remove substations
            for sub_id in delta.get('removed', []):
                current_state.pop(sub_id, None)

            # Update modified substations
            for sub_id, sub in delta.get('modified', {}).items():
                current_state[sub_id] = sub

    # Create latest_snapshot in old format
    substations = list(current_state.values())

    return {
        'version': data.get('version'),
        'generated_at': data.get('generated_at'),
        'metadata': data.get('metadata'),
        'snapshots': snapshots,
        'change_log': data.get('change_log', []),
        'latest_snapshot': {
            'date': snapshots[-1].get('date') if snapshots else None,
            'substations': substations,
            'metadata': {
                'num_substations': len(substations)
            }
        }
    }


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
            return 'blue'
        elif '> 25' in str(capacity_str) or '>= 25' in str(capacity_str):
            return 'green'
        else:
            return 'gray'

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


def compare_two_snapshots(snapshot1, snapshot2):
    """
    Compare two arbitrary snapshots and return changes.

    Args:
        snapshot1: Earlier snapshot dict
        snapshot2: Later snapshot dict

    Returns:
        Changes dict with added, removed, and modified substations
    """
    if not snapshot1 or not snapshot2:
        return None

    # Index substations by IDRPoste for comparison
    subs1 = {
        sub['properties']['IDRPoste']: sub
        for sub in snapshot1.get('substations', [])
    }
    subs2 = {
        sub['properties']['IDRPoste']: sub
        for sub in snapshot2.get('substations', [])
    }

    # Find added and removed
    ids1 = set(subs1.keys())
    ids2 = set(subs2.keys())

    added_ids = ids2 - ids1
    removed_ids = ids1 - ids2
    common_ids = ids1 & ids2

    # Find modified
    modified = []
    for sub_id in common_ids:
        props1 = subs1[sub_id]['properties']
        props2 = subs2[sub_id]['properties']

        # Check if capacity fields changed
        if (props1.get('CapaciteSansContrainte') != props2.get('CapaciteSansContrainte') or
            props1.get('CapacitePosteGabarit') != props2.get('CapacitePosteGabarit') or
            props1.get('Gabarit') != props2.get('Gabarit') or
            props1.get('DemandeProximite') != props2.get('DemandeProximite')):

            modified.append({
                'IDRPoste': sub_id,
                'ADRPoste': props2.get('ADRPoste'),
                'NomCommune': props2.get('NomCommune'),
                'changes': {
                    'CapaciteSansContrainte': {
                        'old': props1.get('CapaciteSansContrainte'),
                        'new': props2.get('CapaciteSansContrainte')
                    },
                    'CapacitePosteGabarit': {
                        'old': props1.get('CapacitePosteGabarit'),
                        'new': props2.get('CapacitePosteGabarit')
                    },
                    'Gabarit': {
                        'old': props1.get('Gabarit'),
                        'new': props2.get('Gabarit')
                    },
                    'DemandeProximite': {
                        'old': props1.get('DemandeProximite'),
                        'new': props2.get('DemandeProximite')
                    }
                }
            })

    return {
        'date': snapshot2.get('date'),
        'added': len(added_ids),
        'removed': len(removed_ids),
        'modified': modified,
        'added_substations': [subs2[sid]['properties'] for sid in added_ids],
        'removed_substations': [subs1[sid]['properties'] for sid in removed_ids],
        'summary': f"{len(added_ids)} added, {len(removed_ids)} removed, {len(modified)} modified"
    }


def create_rte_changes_map(changes_data, snapshot_data, previous_snapshot_data=None, center_lat=46.603354, center_lon=1.888334, zoom_start=6):
    """
    Create a Folium map showing only substations that changed.

    Args:
        changes_data: Changes dict with 'modified', 'added_substations', 'removed_substations'
        snapshot_data: Current snapshot for coordinate lookup
        previous_snapshot_data: Previous snapshot for removed substations coordinates
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

    # Also index previous snapshot for removed substations
    if previous_snapshot_data and 'substations' in previous_snapshot_data:
        for feature in previous_snapshot_data['substations']:
            coords = feature.get('geometry', {}).get('coordinates', [])
            props = feature.get('properties', {})
            sub_id = props.get('IDRPoste')
            if sub_id and len(coords) >= 2 and sub_id not in substation_coords:
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
                <h4 style="margin-bottom: 5px; color: purple;">MODIFIÉ</h4>
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
                color='purple',
                fill=True,
                fillColor='purple',
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
                <h4 style="margin-bottom: 5px; color: #8B4513;">NOUVEAU</h4>
                <p style="margin: 2px 0;"><strong>Poste:</strong> {sub.get('ADRPoste', 'N/A')}</p>
                <p style="margin: 2px 0;"><strong>Commune:</strong> {sub.get('NomCommune', 'N/A')}</p>
                <p style="margin: 2px 0;"><strong>Capacité:</strong> {sub.get('CapaciteSansContrainte', 'N/A')}</p>
            </div>
            """

            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color='#8B4513',
                fill=True,
                fillColor='#8B4513',
                fillOpacity=0.8,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"Nouveau: {sub.get('NomCommune', 'N/A')}"
            ).add_to(m)

    # Add removed substations (red)
    for sub in changes_data.get('removed_substations', []):
        sub_id = sub.get('IDRPoste')
        if sub_id in substation_coords:
            lat, lon = substation_coords[sub_id]

            popup_html = f"""
            <div style="font-family: sans-serif; min-width: 200px;">
                <h4 style="margin-bottom: 5px; color: red;">SUPPRIMÉ</h4>
                <p style="margin: 2px 0;"><strong>Poste:</strong> {sub.get('ADRPoste', 'N/A')}</p>
                <p style="margin: 2px 0;"><strong>Commune:</strong> {sub.get('NomCommune', 'N/A')}</p>
                <p style="margin: 2px 0;"><strong>Capacité:</strong> {sub.get('CapaciteSansContrainte', 'N/A')}</p>
            </div>
            """

            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color='red',
                fill=True,
                fillColor='red',
                fillOpacity=0.8,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"Supprimé: {sub.get('NomCommune', 'N/A')}"
            ).add_to(m)

    return m


# ============================================================================
# CAPARESEAU MAP FUNCTIONS
# ============================================================================

def get_capareseau_capacity_color(capacity_value):
    """
    Get marker color based on Capareseau reserved capacity (INFO_CR).

    Args:
        capacity_value: Capacity value (string or number)

    Returns:
        Color string for Folium marker
    """
    if not capacity_value or capacity_value == 'null' or capacity_value == 'N/A':
        return 'gray'

    capacity_str = str(capacity_value).upper()

    # Color scheme matching RTE for consistency
    if '< 5' in capacity_str or capacity_str.startswith('0'):
        return 'orange'
    elif '5' in capacity_str and '10' in capacity_str:
        return 'yellow'
    elif '10' in capacity_str and '25' in capacity_str:
        return 'blue'
    elif '> 25' in capacity_str or '>= 25' in capacity_str:
        return 'green'
    else:
        return 'gray'


def create_capareseau_map(snapshot_data, center_lat=46.603354, center_lon=1.888334, zoom_start=6):
    """
    Create a Folium map showing Capareseau substations for a given snapshot.

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

    # Add markers for each substation
    for sub in snapshot_data['substations']:
        # Extract coordinates from flat X, Y fields
        lat = sub.get('Y')
        lon = sub.get('X')

        if not lat or not lon:
            continue

        # Get substation details
        name = sub.get('name', 'N/A')
        code = sub.get('code', 'N/A')
        territory = sub.get('territory_name', 'N/A')
        htb_type = sub.get('htb_type', 'N/A')

        values = sub.get('values', {})
        # Handle case where values might not be a dict
        if not isinstance(values, dict):
            values = {}

        capacity_reserved = values.get('INFO_CR', 'N/A')
        rate = values.get('INFO_TX', 'N/A')
        availability = values.get('INFO_NA', 'N/A')
        ess3r = values.get('INFO_ESS3R', 'N/A')
        fas3r = values.get('INFO_FAS3R', 'N/A')
        grd1_cdr = values.get('GRD1_CDR', 'N/A')
        rte_cdr = values.get('RTE_CDR', 'N/A')
        transformer = values.get('INFO_TRF', 'N/A')

        color = get_capareseau_capacity_color(capacity_reserved)

        # Create popup content
        popup_html = f"""
        <div style="font-family: sans-serif; min-width: 250px;">
            <h4 style="margin-bottom: 5px; color: #1d1d1f;">{name}</h4>
            <p style="margin: 2px 0; font-size: 0.9em; color: #6e6e73;"><strong>Code:</strong> {code}</p>
            <p style="margin: 2px 0; font-size: 0.9em; color: #6e6e73;"><strong>Région:</strong> {territory}</p>
            <p style="margin: 2px 0; font-size: 0.9em; color: #6e6e73;"><strong>Type HTB:</strong> {htb_type}</p>
            <hr style="margin: 8px 0; border: none; border-top: 1px solid #d2d2d7;">
            <p style="margin: 2px 0;"><strong>Capacité Réservée (CR):</strong> {capacity_reserved}</p>
            <p style="margin: 2px 0;"><strong>Taux (TX):</strong> {rate}</p>
            <p style="margin: 2px 0;"><strong>Disponibilité (NA):</strong> {availability}</p>
            <hr style="margin: 8px 0; border: none; border-top: 1px solid #d2d2d7;">
            <p style="margin: 2px 0; font-size: 0.85em; color: #6e6e73;"><strong>Stockage 3R:</strong> {ess3r}</p>
            <p style="margin: 2px 0; font-size: 0.85em; color: #6e6e73;"><strong>Flexible AC 3R:</strong> {fas3r}</p>
            <p style="margin: 2px 0; font-size: 0.85em; color: #6e6e73;"><strong>GRD1 CDR:</strong> {grd1_cdr}</p>
            <p style="margin: 2px 0; font-size: 0.85em; color: #6e6e73;"><strong>RTE CDR:</strong> {rte_cdr}</p>
            <p style="margin: 2px 0; font-size: 0.85em; color: #6e6e73;"><strong>Transformateur:</strong> {transformer}</p>
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
            tooltip=name
        ).add_to(m)

    return m


def compare_two_capareseau_snapshots(snapshot1, snapshot2):
    """
    Compare two arbitrary Capareseau snapshots and return changes.

    Args:
        snapshot1: Earlier snapshot dict with 'substations' list
        snapshot2: Later snapshot dict with 'substations' list

    Returns:
        Changes dict with added, removed, and modified substations
    """
    if not snapshot1 or not snapshot2:
        return None

    # Index substations by code
    subs1 = {
        sub['code']: sub
        for sub in snapshot1.get('substations', [])
    }
    subs2 = {
        sub['code']: sub
        for sub in snapshot2.get('substations', [])
    }

    # Find added and removed
    ids1 = set(subs1.keys())
    ids2 = set(subs2.keys())

    added_ids = ids2 - ids1
    removed_ids = ids1 - ids2
    common_ids = ids1 & ids2

    # Find modified
    modified = []
    for sub_id in common_ids:
        sub1 = subs1[sub_id]
        sub2 = subs2[sub_id]

        # Check if capacity values changed
        vals1 = sub1.get('values', {})
        vals2 = sub2.get('values', {})

        # Track which fields changed
        changed_fields = {}
        for field in ['INFO_CR', 'INFO_TX', 'INFO_NA', 'INFO_ESS3R', 'INFO_FAS3R',
                     'GRD1_CDR', 'RTE_CDR', 'INFO_TRF']:
            val1 = vals1.get(field) if isinstance(vals1, dict) else None
            val2 = vals2.get(field) if isinstance(vals2, dict) else None
            if val1 != val2:
                changed_fields[field] = {
                    'old': val1,
                    'new': val2
                }

        if changed_fields:
            modified.append({
                'code': sub_id,
                'name': sub2.get('name'),
                'territory_name': sub2.get('territory_name'),
                'X': sub2.get('X'),
                'Y': sub2.get('Y'),
                'changes': changed_fields
            })

    return {
        'date': snapshot2.get('date'),
        'added': len(added_ids),
        'removed': len(removed_ids),
        'modified': modified,
        'added_substations': [subs2[sid] for sid in added_ids],
        'removed_substations': [subs1[sid] for sid in removed_ids],
        'summary': f"{len(added_ids)} added, {len(removed_ids)} removed, {len(modified)} modified"
    }


def create_capareseau_changes_map(changes_data, snapshot_data, previous_snapshot_data=None, center_lat=46.603354, center_lon=1.888334, zoom_start=6):
    """
    Create a Folium map showing only Capareseau substations that changed.

    Args:
        changes_data: Changes dict with 'modified', 'added_substations', 'removed_substations'
        snapshot_data: Current snapshot for coordinate lookup
        previous_snapshot_data: Previous snapshot for removed substations coordinates
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

    # Index current substations by code for coordinate lookup
    substation_coords = {}
    if snapshot_data and 'substations' in snapshot_data:
        for sub in snapshot_data['substations']:
            sub_id = sub.get('code')
            lat = sub.get('Y')
            lon = sub.get('X')
            if sub_id and lat and lon:
                substation_coords[sub_id] = (lat, lon)

    # Also index previous snapshot for removed substations
    if previous_snapshot_data and 'substations' in previous_snapshot_data:
        for sub in previous_snapshot_data['substations']:
            sub_id = sub.get('code')
            lat = sub.get('Y')
            lon = sub.get('X')
            if sub_id and lat and lon and sub_id not in substation_coords:
                substation_coords[sub_id] = (lat, lon)

    # Add modified substations (purple)
    for change in changes_data.get('modified', []):
        sub_id = change.get('code')
        lat = change.get('Y')
        lon = change.get('X')

        if not lat or not lon:
            if sub_id in substation_coords:
                lat, lon = substation_coords[sub_id]
            else:
                continue

        # Build change details
        changes_list = []
        for field, vals in change.get('changes', {}).items():
            old_val = vals.get('old', 'N/A')
            new_val = vals.get('new', 'N/A')
            changes_list.append(f"<li><strong>{field}:</strong> {old_val} → {new_val}</li>")

        changes_html = ''.join(changes_list)

        popup_html = f"""
        <div style="font-family: sans-serif; min-width: 280px;">
            <h4 style="margin-bottom: 5px; color: purple;">MODIFIÉ</h4>
            <p style="margin: 2px 0;"><strong>Poste:</strong> {change.get('name', 'N/A')}</p>
            <p style="margin: 2px 0;"><strong>Code:</strong> {change.get('code', 'N/A')}</p>
            <p style="margin: 2px 0;"><strong>Région:</strong> {change.get('territory_name', 'N/A')}</p>
            <hr style="margin: 5px 0;">
            <ul style="margin: 5px 0; padding-left: 20px;">
                {changes_html}
            </ul>
        </div>
        """

        folium.CircleMarker(
            location=[lat, lon],
            radius=8,
            color='purple',
            fill=True,
            fillColor='purple',
            fillOpacity=0.8,
            popup=folium.Popup(popup_html, max_width=350),
            tooltip=f"Modifié: {change.get('name', 'N/A')}"
        ).add_to(m)

    # Add added substations (brown)
    for sub in changes_data.get('added_substations', []):
        lat = sub.get('Y')
        lon = sub.get('X')

        if not lat or not lon:
            continue

        values = sub.get('values', {})
        capacity = values.get('INFO_CR', 'N/A') if isinstance(values, dict) else 'N/A'

        popup_html = f"""
        <div style="font-family: sans-serif; min-width: 250px;">
            <h4 style="margin-bottom: 5px; color: #8B4513;">NOUVEAU</h4>
            <p style="margin: 2px 0;"><strong>Poste:</strong> {sub.get('name', 'N/A')}</p>
            <p style="margin: 2px 0;"><strong>Code:</strong> {sub.get('code', 'N/A')}</p>
            <p style="margin: 2px 0;"><strong>Région:</strong> {sub.get('territory_name', 'N/A')}</p>
            <p style="margin: 2px 0;"><strong>Capacité:</strong> {capacity}</p>
        </div>
        """

        folium.CircleMarker(
            location=[lat, lon],
            radius=8,
            color='#8B4513',
            fill=True,
            fillColor='#8B4513',
            fillOpacity=0.8,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"Nouveau: {sub.get('name', 'N/A')}"
        ).add_to(m)

    # Add removed substations (red)
    for sub in changes_data.get('removed_substations', []):
        sub_id = sub.get('code')
        if sub_id in substation_coords:
            lat, lon = substation_coords[sub_id]

            values = sub.get('values', {})
            capacity = values.get('INFO_CR', 'N/A') if isinstance(values, dict) else 'N/A'

            popup_html = f"""
            <div style="font-family: sans-serif; min-width: 250px;">
                <h4 style="margin-bottom: 5px; color: red;">SUPPRIMÉ</h4>
                <p style="margin: 2px 0;"><strong>Poste:</strong> {sub.get('name', 'N/A')}</p>
                <p style="margin: 2px 0;"><strong>Code:</strong> {sub.get('code', 'N/A')}</p>
                <p style="margin: 2px 0;"><strong>Région:</strong> {sub.get('territory_name', 'N/A')}</p>
                <p style="margin: 2px 0;"><strong>Capacité:</strong> {capacity}</p>
            </div>
            """

            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color='red',
                fill=True,
                fillColor='red',
                fillOpacity=0.8,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"Supprimé: {sub.get('name', 'N/A')}"
            ).add_to(m)

    return m


# ============================================================================
# MAIN APP
# ============================================================================

# Load data
data = load_data()

# Header
st.title("Plateforme d'analyse")
st.markdown("Projets d'énergies renouvelables et capacités d'accueil réseau")

# Create tabs
tab1, tab2, tab3 = st.tabs(["📊 PV / Éolien", "🔋 CartoStock", "⚡ Capareseau"])

# ============================================================================
# TAB 1: PV / ÉOLIEN (ENEDIS QUEUE DATA)
# ============================================================================

with tab1:
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
# TAB 2: RTE CARTOSTOCK SECTION
# ============================================================================

with tab2:
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
        
            # Date selection for state map and comparison
            st.markdown("")
            snapshots = rte_data['snapshots']
            # Parse dates with error handling for malformed timestamps
            snapshot_dates = []
            for s in snapshots:
                try:
                    date_str = s['date']
                    # Handle malformed dates with double timezone suffix
                    if '+00:00+00:00' in date_str:
                        date_str = date_str.replace('+00:00+00:00', '')
                    if '+00:00Z' in date_str:
                        date_str = date_str.replace('+00:00Z', 'Z')
                    snapshot_dates.append(datetime.fromisoformat(date_str.replace('Z', '+00:00')))
                except:
                    # Use a placeholder date if parsing fails
                    snapshot_dates.append(datetime.now())
            date_labels = [d.strftime('%d/%m/%Y %H:%M') for d in snapshot_dates]
        
            # Two columns for the two maps
            st.markdown("")
            col_map1, col_map2 = st.columns(2)
        
            with col_map1:
                st.markdown("### État des Postes")
                st.caption("Vue d'ensemble de tous les postes et leur capacité disponible")
        
                # Date selector for state map
                if len(snapshot_dates) > 1:
                    state_date_idx = st.selectbox(
                        "📅 Date pour l'état:",
                        options=range(len(snapshots)),
                        format_func=lambda i: date_labels[i],
                        index=len(snapshots) - 1,
                        key="state_date"
                    )
                else:
                    state_date_idx = 0
                    st.info(f"📅 Snapshot unique du {date_labels[0]} UTC")
        
                selected_snapshot = snapshots[state_date_idx]
        
                # Create and display state map with loading indicator
                with st.spinner('Chargement de la carte...'):
                    state_map = create_rte_map(selected_snapshot)
                    st_folium(state_map, width=550, height=500, key=f"state_map_{state_date_idx}", returned_objects=[])
        
                # Legend
                st.markdown("""
                **Légende:**
                - 🟢 Vert : > 25 MW
                - 🔵 Bleu : 10-25 MW
                - 🟡 Jaune : 5-10 MW
                - 🟠 Orange : < 5 MW
                - ⚫ Gris : Aucune capacité
                """)
        
            with col_map2:
                st.markdown("### Changements")
                st.caption("Comparer deux dates pour voir les changements")
        
                # Date comparison selectors
                if len(snapshot_dates) > 1:
                    col_date1, col_date2 = st.columns(2)
        
                    with col_date1:
                        date1_idx = st.selectbox(
                            "📅 Date 1 (avant):",
                            options=range(len(snapshots)),
                            format_func=lambda i: date_labels[i],
                            index=max(0, len(snapshots) - 2),
                            key="compare_date1"
                        )
        
                    with col_date2:
                        date2_idx = st.selectbox(
                            "📅 Date 2 (après):",
                            options=range(len(snapshots)),
                            format_func=lambda i: date_labels[i],
                            index=len(snapshots) - 1,
                            key="compare_date2"
                        )
        
                    if date1_idx == date2_idx:
                        st.warning("⚠️ Veuillez sélectionner deux dates différentes pour la comparaison")
                    else:
                        # Compare the two selected snapshots
                        snapshot1 = snapshots[date1_idx]
                        snapshot2 = snapshots[date2_idx]
        
                        comparison_changes = compare_two_snapshots(snapshot1, snapshot2)
        
                        if comparison_changes and (comparison_changes.get('added') > 0 or
                                                  comparison_changes.get('removed') > 0 or
                                                  len(comparison_changes.get('modified', [])) > 0):
                            # Create and display changes map with loading indicator
                            with st.spinner('Calcul des changements...'):
                                changes_map = create_rte_changes_map(comparison_changes, snapshot2, snapshot1)
                                st_folium(changes_map, width=550, height=500, key=f"changes_map_{date1_idx}_{date2_idx}", returned_objects=[])
        
                            # Summary
                            st.markdown(f"""
                            **Résumé:**
                            - ✅ Ajoutés: {comparison_changes['added']}
                            - ❌ Supprimés: {comparison_changes['removed']}
                            - 🔄 Modifiés: {len(comparison_changes.get('modified', []))}
                            """)
                        else:
                            st.info("Aucun changement détecté entre ces deux dates")
                else:
                    st.info("Un seul snapshot disponible - attendez la prochaine collecte pour voir les changements")
        
                # Legend for changes
                st.markdown("""
                **Légende:**
                - 🟣 Violet : Modifié
                - 🔴 Rouge : Supprimé
                - 🟤 Marron : Nouveau
                """)
        
            # Changes table
            if len(snapshot_dates) > 1 and 'date1_idx' in locals() and 'date2_idx' in locals() and date1_idx != date2_idx:
                comparison_changes = compare_two_snapshots(snapshots[date1_idx], snapshots[date2_idx])
        
                if comparison_changes and len(comparison_changes.get('modified', [])) > 0:
                    st.markdown("")
                    st.markdown("### Détails des Modifications")
        
                    changes_list = []
                    for change in comparison_changes['modified']:
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
    st.caption("Source RTE : [CartoStock](https://cartostock.cloud-rte-france.com/) • Données collectées automatiquement **chaque jour à 6h30 UTC**")

# ============================================================================
# TAB 3: CAPARESEAU SECTION
# ============================================================================

with tab3:
    st.markdown("## Capareseau")
    st.markdown("Capacités d'accueil aux réseaux de transport et de distribution")

    # Load Capareseau data
    capareseau_data = load_capareseau_data()

    if capareseau_data and capareseau_data.get('snapshots'):
        # Capareseau Data freshness
        st.markdown("")
        col1, col2, col3 = st.columns(3)

        generated_at_cap = datetime.fromisoformat(capareseau_data['generated_at'].replace('Z', '+00:00'))
        days_since_generated_cap = (datetime.now(timezone.utc) - generated_at_cap).days

        with col1:
            st.metric(
                "Dernière Collecte",
                f"Il y a {days_since_generated_cap} jour{'s' if days_since_generated_cap > 1 else ''}",
                delta=None
            )
            st.caption(f"{generated_at_cap.strftime('%d/%m/%Y à %H:%M')} UTC")

        with col2:
            st.metric(
                "Postes Disponibles",
                f"{capareseau_data['metadata']['latest_substations']:,}",
                delta=None,
                help="Nombre de postes avec capacité d'accueil pour raccordement production"
            )
            st.caption("12 régions françaises")

        with col3:
            st.metric(
                "Historique",
                f"{capareseau_data['metadata']['total_snapshots']} snapshots",
                delta=None,
                help="Nombre de collectes de données historiques"
            )
            if capareseau_data.get('change_log') and len(capareseau_data['change_log']) > 0:
                latest_change = capareseau_data['change_log'][-1]
                st.caption(f"Dernier: {latest_change['summary']}")

        # Map Visualization
        st.markdown("")
        st.markdown("### 📍 Visualisation Cartographique")

        if capareseau_data and capareseau_data.get('snapshots'):
            snapshots = capareseau_data['snapshots']

            # Parse snapshot dates
            snapshot_dates = []
            for s in snapshots:
                try:
                    date_str = s.get('date', '')
                    if date_str:
                        # Handle malformed dates with double timezone suffix
                        # Replace double +00:00+00:00 or +00:00Z with just Z
                        if '+00:00+00:00' in date_str:
                            date_str = date_str.replace('+00:00+00:00', '')
                        if '+00:00Z' in date_str:
                            date_str = date_str.replace('+00:00Z', 'Z')

                        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        snapshot_dates.append(dt)
                    else:
                        snapshot_dates.append(None)
                except:
                    # Use placeholder for malformed dates
                    snapshot_dates.append(None)

            date_labels = [d.strftime('%d/%m/%Y %H:%M') if d else 'N/A' for d in snapshot_dates]

            # Two columns for maps
            col_map1, col_map2 = st.columns(2)

            with col_map1:
                st.markdown("#### État des Postes")
                st.caption("Vue d'ensemble de tous les postes et leur capacité disponible")

                # Date selector for state map
                if len(snapshots) > 1:
                    state_date_idx = st.selectbox(
                        "📅 Date pour l'état:",
                        options=range(len(snapshots)),
                        format_func=lambda i: date_labels[i],
                        index=len(snapshots) - 1,
                        key="capareseau_state_date"
                    )
                else:
                    state_date_idx = 0
                    if len(snapshots) == 1 and snapshot_dates[0]:
                        st.info(f"📅 Snapshot unique du {date_labels[0]} UTC")

                # Get selected snapshot
                selected_snapshot = snapshots[state_date_idx]

                # Reconstruct if delta format
                if selected_snapshot.get('type') == 'delta':
                    # Need to reconstruct from base + all deltas up to this point
                    base_snapshot = capareseau_data.get('base_snapshot', {})
                    reconstructed = {'substations': list(base_snapshot.get('substations', []))}

                    # Apply deltas in order
                    for snap in snapshots[:state_date_idx + 1]:
                        if snap.get('type') == 'base':
                            reconstructed = {'substations': snap.get('data', {}).get('substations', [])}
                        elif snap.get('type') == 'delta':
                            delta = snap.get('data', {})
                            subs_dict = {sub['code']: sub for sub in reconstructed.get('substations', [])}

                            # Apply delta
                            for sub in delta.get('added', []):
                                subs_dict[sub['code']] = sub
                            for sub_id in delta.get('removed', []):
                                subs_dict.pop(sub_id, None)
                            for sub_id, sub in delta.get('modified', {}).items():
                                subs_dict[sub_id] = sub

                            reconstructed = {'substations': list(subs_dict.values())}

                    display_snapshot = reconstructed
                elif selected_snapshot.get('type') == 'base':
                    display_snapshot = selected_snapshot.get('data', {})
                else:
                    # Old format
                    display_snapshot = selected_snapshot

                # Create and display state map
                if display_snapshot and display_snapshot.get('substations'):
                    with st.spinner('Chargement de la carte...'):
                        state_map = create_capareseau_map(display_snapshot)
                        st_folium(state_map, width=550, height=500, key=f"capareseau_state_map_{state_date_idx}", returned_objects=[])

                    # Legend
                    st.markdown("""
                    **Légende:**
                    - 🟢 Vert : > 25 MW
                    - 🔵 Bleu : 10-25 MW
                    - 🟡 Jaune : 5-10 MW
                    - 🟠 Orange : < 5 MW
                    - ⚫ Gris : Aucune capacité / Données indisponibles
                    """)

                    st.caption(f"**{len(display_snapshot['substations'])} postes sources** affichés")

            with col_map2:
                st.markdown("#### Changements")
                st.caption("Comparer deux dates pour voir les changements")

                # Date comparison selectors
                if len(snapshots) > 1:
                    col_date1, col_date2 = st.columns(2)

                    with col_date1:
                        date1_idx = st.selectbox(
                            "📅 Date 1 (avant):",
                            options=range(len(snapshots)),
                            format_func=lambda i: date_labels[i],
                            index=max(0, len(snapshots) - 2),
                            key="capareseau_compare_date1"
                        )

                    with col_date2:
                        date2_idx = st.selectbox(
                            "📅 Date 2 (après):",
                            options=range(len(snapshots)),
                            format_func=lambda i: date_labels[i],
                            index=len(snapshots) - 1,
                            key="capareseau_compare_date2"
                        )

                    if date1_idx == date2_idx:
                        st.warning("⚠️ Veuillez sélectionner deux dates différentes pour la comparaison")
                    else:
                        # Reconstruct both snapshots
                        snap1 = snapshots[date1_idx]
                        snap2 = snapshots[date2_idx]

                        # Reconstruct snapshot 1
                        if snap1.get('type') in ['delta', 'base']:
                            base_snapshot = capareseau_data.get('base_snapshot', {})
                            reconstructed1 = {'substations': list(base_snapshot.get('substations', []))}

                            for snap in snapshots[:date1_idx + 1]:
                                if snap.get('type') == 'base':
                                    reconstructed1 = {'substations': snap.get('data', {}).get('substations', [])}
                                elif snap.get('type') == 'delta':
                                    delta = snap.get('data', {})
                                    subs_dict = {sub['code']: sub for sub in reconstructed1.get('substations', [])}
                                    for sub in delta.get('added', []):
                                        subs_dict[sub['code']] = sub
                                    for sub_id in delta.get('removed', []):
                                        subs_dict.pop(sub_id, None)
                                    for sub_id, sub in delta.get('modified', {}).items():
                                        subs_dict[sub_id] = sub
                                    reconstructed1 = {'substations': list(subs_dict.values())}
                            display_snap1 = reconstructed1
                        else:
                            display_snap1 = snap1

                        # Reconstruct snapshot 2
                        if snap2.get('type') in ['delta', 'base']:
                            base_snapshot = capareseau_data.get('base_snapshot', {})
                            reconstructed2 = {'substations': list(base_snapshot.get('substations', []))}

                            for snap in snapshots[:date2_idx + 1]:
                                if snap.get('type') == 'base':
                                    reconstructed2 = {'substations': snap.get('data', {}).get('substations', [])}
                                elif snap.get('type') == 'delta':
                                    delta = snap.get('data', {})
                                    subs_dict = {sub['code']: sub for sub in reconstructed2.get('substations', [])}
                                    for sub in delta.get('added', []):
                                        subs_dict[sub['code']] = sub
                                    for sub_id in delta.get('removed', []):
                                        subs_dict.pop(sub_id, None)
                                    for sub_id, sub in delta.get('modified', {}).items():
                                        subs_dict[sub_id] = sub
                                    reconstructed2 = {'substations': list(subs_dict.values())}
                            display_snap2 = reconstructed2
                        else:
                            display_snap2 = snap2

                        # Compare snapshots
                        changes = compare_two_capareseau_snapshots(display_snap1, display_snap2)

                        if changes:
                            with st.spinner('Chargement de la carte des changements...'):
                                changes_map = create_capareseau_changes_map(
                                    changes,
                                    display_snap2,
                                    display_snap1
                                )
                                st_folium(changes_map, width=550, height=500, key=f"capareseau_changes_map_{date1_idx}_{date2_idx}", returned_objects=[])

                            # Legend
                            st.markdown("""
                            **Légende:**
                            - 🟣 Violet : Modifié
                            - 🔴 Rouge : Supprimé
                            - 🟤 Marron : Nouveau
                            """)

                            st.caption(f"**{changes['summary']}**")

                            # Show detailed changes table
                            if changes.get('modified'):
                                st.markdown("**Détails des modifications:**")
                                changes_list = []
                                for change in changes['modified']:
                                    for field, vals in change.get('changes', {}).items():
                                        if vals['old'] != vals['new']:
                                            changes_list.append({
                                                'Poste': change.get('name', 'N/A'),
                                                'Région': change.get('territory_name', 'N/A'),
                                                'Champ': field,
                                                'Ancienne Valeur': vals['old'],
                                                'Nouvelle Valeur': vals['new']
                                            })

                                if changes_list:
                                    df_changes = pd.DataFrame(changes_list)
                                    st.dataframe(df_changes, use_container_width=True, hide_index=True)
                else:
                    st.info("Un seul snapshot disponible - attendez la prochaine collecte pour voir les changements")

                    # Legend anyway
                    st.markdown("""
                    **Légende:**
                    - 🟣 Violet : Modifié
                    - 🔴 Rouge : Supprimé
                    - 🟤 Marron : Nouveau
                    """)

    else:
        st.info("Les données Capareseau ne sont pas encore disponibles. Elles seront ajoutées lors de la prochaine collecte automatique.")

    # Footer
    st.markdown("")
    st.caption("Source : [Capareseau](https://www.capareseau.fr/) • Données collectées automatiquement **chaque jour à 6h30 UTC**")
