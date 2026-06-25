"""3D Initial Logo Maker with Interactive Streamlit GUI (Grid Button Version).

This script runs a web application where users can click letter buttons
to select initials, generate a 3D intersection mesh using SDF + Marching Cubes,
and visualize the result immediately in 3D.
"""

import base64
import os
import string
from typing import Tuple

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage import measure
import streamlit as st

DEFAULT_SIZE = 200
TEMPLATE_FILE = "viewer_template.html"


def load_signed_distance_field(
    path: str,
    size: int,
) -> np.ndarray:
    """Loads an image and computes a resized signed distance field.

    Args:
        path: Source image path.
        size: Target resolution.

    Returns:
        Signed distance field.
    """
    img = Image.open(path).convert("1")
    mask = np.array(img)

    dist_outside = ndimage.distance_transform_edt(mask)
    dist_inside = ndimage.distance_transform_edt(~mask)

    sdf = np.where(
        mask,
        -dist_outside,
        dist_inside,
    ).astype(np.float64)

    if sdf.shape != (size, size):
        zoom_factor = (
            size / sdf.shape[0],
            size / sdf.shape[1],
        )

        sdf = ndimage.zoom(
            sdf,
            zoom_factor,
            order=1,
        )

    return sdf


def extrude_to_3d(
    sdf2d: np.ndarray,
    axis: str,
) -> np.ndarray:
    """Extrudes a 2D SDF into a 3D scalar field."""
    size = sdf2d.shape[0]

    if axis == "z":
        return np.broadcast_to(
            sdf2d[:, :, np.newaxis],
            (size, size, size),
        ).copy()

    if axis == "y":
        return np.broadcast_to(
            sdf2d[:, np.newaxis, :],
            (size, size, size),
        ).copy()

    raise ValueError("axis must be 'y' or 'z'")


def build_mesh_from_sdf(sdf_field: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Applies Marching Cubes to a 3D SDF to generate a surface mesh."""
    verts, faces, _, _ = measure.marching_cubes(sdf_field, level=0.0)
    faces = faces[:, [0, 2, 1]]  # Reverse winding order to fix normal direction
    return verts, faces


def write_obj(path: str, vertices: np.ndarray, faces: np.ndarray) -> None:
    """Writes vertices and faces directly to a Wavefront OBJ file."""
    with open(path, "w") as f:
        for v in vertices:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for face in faces:
            f.write(f"f {face[0] + 1} {face[1] + 1} {face[2] + 1}\n")


def render_3d_viewer(obj_path: str, obj_filename: str) -> None:
    """Reads the generated OBJ file, injects it into the HTML template, and renders it."""
    if not os.path.exists(TEMPLATE_FILE):
        st.error(f"Required template file '{TEMPLATE_FILE}' not found.")
        return

    if not os.path.exists(obj_path):
        return

    with open(obj_path, "r", encoding="utf-8") as f:
        obj_data = f.read()

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        html_template = f.read()

    b64_obj_data = base64.b64encode(obj_data.encode("utf-8")).decode("utf-8")
    final_html = html_template.replace("{{obj_data}}", b64_obj_data)
    final_html = final_html.replace("{{obj_filename}}", obj_filename)

    st.iframe(final_html, height=550)


def main() -> None:
    st.set_page_config(page_title="3D Initial Logo Studio", layout="centered")

    st.title("3D Initial Logo Studio")
    st.write("Click letters to select your initials and generate a 3D logo.")

    # Initialize session state for selected characters
    if "char_first" not in st.session_state:
        st.session_state["char_first"] = "A"
    if "char_last" not in st.session_state:
        st.session_state["char_last"] = "B"

    # Sidebar / Control panel
    st.sidebar.header("Configuration")

    # 1. First Character Selection Grid (Z-extrusion)
    st.sidebar.markdown("**First Character**")
    alphabet = list(string.ascii_uppercase)
    
    # Render A-Z in a 4-column grid (more stable on narrow mobile screens)
    cols_first = st.sidebar.columns(4)
    for i, letter in enumerate(alphabet):
        col = cols_first[i % 4]
        # Use primary style if currently selected
        is_selected = st.session_state["char_first"] == letter
        btn_type = "primary" if is_selected else "secondary"
        
        if col.button(letter, key=f"btn_f_{letter}", type=btn_type, use_container_width=True):
            st.session_state["char_first"] = letter
            st.rerun()

    st.sidebar.markdown("---")

    # 2. Second Character Selection Grid (Y-extrusion)
    st.sidebar.markdown("**Second Character**")
    cols_last = st.sidebar.columns(4)
    for i, letter in enumerate(alphabet):
        col = cols_last[i % 4]
        is_selected = st.session_state["char_last"] == letter
        btn_type = "primary" if is_selected else "secondary"
        
        if col.button(letter, key=f"btn_l_{letter}", type=btn_type, use_container_width=True):
            st.session_state["char_last"] = letter
            st.rerun()

    st.sidebar.markdown("---")

    # 3. Grid resolution setting (Max restricted to 200)
    grid_size = st.sidebar.slider(
        "Voxel Grid Resolution",
        min_value=50,
        max_value=200,
        value=DEFAULT_SIZE,
        step=10,
        help="Matches your 200x200 source images."
    )
    
    output_filename = "logo.obj"

    st.sidebar.markdown("---")

    # Action Button
    if st.sidebar.button("Generate 3D Mesh ✨", type="primary", use_container_width=True):
        with st.spinner("Calculating SDF fields and extracting mesh..."):
            try:
                first_img_path = f"images/{st.session_state['char_first'].lower()}.png"
                last_img_path = f"images/{st.session_state['char_last'].lower()}.png"

                if not os.path.exists(first_img_path) or not os.path.exists(last_img_path):
                    st.error(f"Missing source images: '{first_img_path}' or '{last_img_path}' not found.")
                    return

                # Mesh Generation Pipeline
                sdf2d_first = load_signed_distance_field(
                    first_img_path,
                    grid_size,
                )

                sdf2d_last = load_signed_distance_field(
                    last_img_path,
                    grid_size,
                )

                sdf_field1 = extrude_to_3d(sdf2d_first, axis="z")
                sdf_field2 = extrude_to_3d(sdf2d_last, axis="y")

                combined_sdf = np.maximum(sdf_field1, sdf_field2)
                verts, faces = build_mesh_from_sdf(combined_sdf)
                verts = verts - grid_size / 2.0

                write_obj(output_filename, verts, faces)
                st.success(f"Generated! ({len(verts)} vertices)")

            except Exception as e:
                st.error(f"An error occurred: {e}")

    # Main Panel Viewer Render
    if os.path.exists(output_filename):
        st.subheader(f"Current Model: {st.session_state['char_first']} + {st.session_state['char_last']}")
        
        obj_filename = f"{st.session_state['char_first']}{st.session_state['char_last']}.obj"
        render_3d_viewer(output_filename, obj_filename)
    else:
        st.info("Select letters from the sidebar grid and click 'Generate 3D Mesh' to begin.")


if __name__ == "__main__":
    main()