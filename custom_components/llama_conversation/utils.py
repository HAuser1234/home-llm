import time
import os
import sys
import platform
import logging
import voluptuous as vol
import webcolors
from importlib.metadata import version
from huggingface_hub import hf_hub_download, HfFileSystem

from homeassistant.requirements import pip_kwargs
from homeassistant.util.package import install_package, is_installed

from .const import (
    INTEGRATION_VERSION,
    EMBEDDED_LLAMA_CPP_PYTHON_VERSION,
)

_LOGGER = logging.getLogger(__name__)

def closest_color(requested_color):
    min_colors = {}
    for key, name in webcolors.CSS3_HEX_TO_NAMES.items():
        r_c, g_c, b_c = webcolors.hex_to_rgb(key)
        rd = (r_c - requested_color[0]) ** 2
        gd = (g_c - requested_color[1]) ** 2
        bd = (b_c - requested_color[2]) ** 2
        min_colors[(rd + gd + bd)] = name
    return min_colors[min(min_colors.keys())]

def flatten_vol_schema(schema):
    flattened = []
    def _flatten(current_schema, prefix=''):
        if isinstance(current_schema, vol.Schema):
            if isinstance(current_schema.schema, vol.validators._WithSubValidators):
                for subval in current_schema.schema.validators:
                    _flatten(subval, prefix)
            elif isinstance(current_schema.schema, dict):
                for key, val in current_schema.schema.items():
                    _flatten(val, prefix + str(key) + '/')
        elif isinstance(current_schema, vol.validators._WithSubValidators):
            for subval in current_schema.validators:
                _flatten(subval, prefix)
        elif callable(current_schema):
            flattened.append(prefix[:-1] if prefix else prefix)
    _flatten(schema)
    return flattened

def download_model_from_hf(model_name: str, quantization_type: str, storage_folder: str):
    fs = HfFileSystem()
    potential_files = [ f for f in fs.glob(f"{model_name}/*.gguf") ]
    wanted_file = [f for f in potential_files if (f".{quantization_type.lower()}." in f or f".{quantization_type.upper()}." in f)]

    if len(wanted_file) != 1:
        raise Exception(f"The quantization '{quantization_type}' does not exist in the HF repo for {model_name}")

    try:
        os.makedirs(storage_folder, exist_ok=True)
    except Exception as ex:
        raise Exception(f"Failed to create the required folder for storing models! You may need to create the path '{storage_folder}' manually.") from ex

    return hf_hub_download(
        repo_id=model_name,
        repo_type="model",
        filename=wanted_file[0].removeprefix(model_name + "/"),
        resume_download=True,
        cache_dir=storage_folder,
    )

def install_llama_cpp_python(config_dir: str):

    if is_installed("llama-cpp-python"):
        return True
    
    platform_suffix = platform.machine()
    if platform_suffix == "arm64":
        platform_suffix = "aarch64"

    runtime_version = f"cp{sys.version_info.major}{sys.version_info.minor}"
    
    folder = os.path.dirname(__file__)
    potential_wheels = sorted([ path for path in os.listdir(folder) if path.endswith(f"{platform_suffix}.whl") ], reverse=True)
    potential_wheels = [ wheel for wheel in potential_wheels if runtime_version in wheel ]
    if len(potential_wheels) > 0:

        latest_wheel = potential_wheels[0]

        _LOGGER.info("Installing llama-cpp-python from local wheel")
        _LOGGER.debug(f"Wheel location: {latest_wheel}")
        return install_package(os.path.join(folder, latest_wheel), pip_kwargs(config_dir))
    
    instruction_extensions_suffix = ""
    if platform_suffix == "amd64" or platform_suffix == "i386":
        with open("/proc/cpuinfo") as f:
            cpu_features = [ line for line in f.readlines() if line.startswith("Features") or line.startswith("flags")][0]
        if "avx512f" in cpu_features and "avx512bw" in cpu_features:
            instruction_extensions_suffix = "-avx512"
        elif "avx" not in cpu_features:
            instruction_extensions_suffix = "-noavx"
        
    github_release_url = f"https://github.com/HAuser1234/home-llm/releases/download/v{INTEGRATION_VERSION}/llama_cpp_python-{EMBEDDED_LLAMA_CPP_PYTHON_VERSION}-{runtime_version}-{runtime_version}-musllinux_1_2_{platform_suffix}{instruction_extensions_suffix}.whl"
    if install_package(github_release_url, pip_kwargs(config_dir)):
        _LOGGER.info("llama-cpp-python successfully installed from GitHub release")
        return True
    
    _LOGGER.error(
        "Error installing llama-cpp-python. Could not install the binary wheels from GitHub for " + \
        f"platform: {platform_suffix}, python version: {sys.version_info.major}.{sys.version_info.minor}. " + \
        "Please manually build or download the wheels and place them in the `/config/custom_components/llama_conversation` directory." + \
        "Make sure that you download the correct .whl file for your platform and python version from the GitHub releases page."
    )
    return False
    

