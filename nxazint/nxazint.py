from collections.abc import Iterable
from datetime import datetime
import h5py
import numpy as np
from enum import Enum
import azint
import os
import logging
from . import __version__

DEFAULT_LOG_LEVEL = "INFO"

log_level = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}
numeric_level = LOG_LEVELS.get(log_level, logging.INFO)
logging.basicConfig(
    level=numeric_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

class BLNames(Enum):
    BALDER = "Balder"
    BIOMAX = "BioMAX"
    BLOCH = "Bloch"
    COSAXS = "CoSAXS"
    DANMAX = "DanMAX"
    FEMTOMAX = "FemtoMAX"
    FINEST = "FinEst"
    FLEXPES = "FlexPES"
    FORMAX = "ForMAX"
    HIPPIE = "HIPPIE"
    MAXPEEM = "MAXPEEM"
    MICROMAX = "MicroMAX"
    NANOMAX = "NanoMAX"
    SEDSMAX = "SedsMAX"
    SOFTIMAX = "SoftiMAX"
    SPECIES = "SPECIES"
    VERITAS = "Veritas"

class NX_writer():
    def __init__(self, ai, output_file):
        self.ai = ai
        self.output_file = output_file
        self.fh = None
        self.config = None
        with h5py.File(self.output_file, "w") as fh_w:
            self.fh = fh_w
            if "entry" not in fh_w: # this condition can be omitted, check that
                self.write_header()
        
    def write_header(self):
        logging.info(f"writing header started, azint version is {azint.__version__}")

        entry = self.fh.create_group("entry", track_order=True)
        entry.attrs["NX_class"] = "NXentry"
        entry.attrs["default"] = "data" 
        logging.debug("entry is created in the file")


        if self.ai.azimuth_axis is None:
            logging.info("azimuth_axis is None, creating NXazint1d")
            definition = entry.create_dataset("definition", data="NXazint1d")
            definition.attrs["type"] = "NX_CHAR"
        
        solid_angle = entry.create_dataset("solid_angle_applied", data=True if self.ai.solid_angle else False)
        solid_angle.attrs["type"] = "NX_BOOLEAN"

        polarization = self.ai.polarization_factor if self.ai.polarization_factor is not None else 0
        polarization_applied = entry.create_dataset("polarization_applied", data=True if self.ai.polarization_factor  is not None else False)
        polarization_applied.attrs["type"] = "NX_BOOLEAN"

        logging.info("solid_angle_applied and polarization_applied data sets are created")
        logging.info(f"solid_angle: {self.ai.solid_angle}")
        logging.info(f"polarization_factor: {self.ai.polarization_factor}")
        

        # Add instrument
        instrument = entry.create_group("instrument", track_order=True)
        instrument.attrs["NX_class"] = "NXinstrument"
        instrument.attrs["default"] = "name" 
        bl_name = self.get_bl_name_from_path(self.ai.poni, BLNames)
        logging.info(f"Beamline: {bl_name}")
        
        instrument["name"] = np.string_(bl_name)
        instrument['name'].attrs["type"] = "NX_CHAR"

        # Add monochromator
        mono = instrument.create_group("monochromator", track_order=True)
        mono.attrs["NX_class"] = "NXmonochromator"
        mono.attrs["default"] = "energy"  

        # Add source
        source = instrument.create_group("source", track_order=True)
        source.attrs["NX_class"] = "NXsource"
        source.attrs["default"] = "name"  
        source['name'] = np.string_("MAX IV")
        source['name'].attrs["type"] = "NX_CHAR"
        source['type'] = np.string_("Synchrotron X-ray Source")
        source['type'].attrs["type"] = "NX_CHAR"
        source['probe'] = np.string_("x-ray")
        source['probe'].attrs["type"] = "NX_CHAR"

        poni_file = self.ai.poni
        if isinstance(self.ai.poni, str):
            with open(poni_file, "r") as pf:
                try:
                    logging.info(f"Reading poni file ...")
                    ponif = pf.read()
                    wavelength_found = False
                    for line in ponif.splitlines():
                        if line.startswith("Wavelength:"):
                            wlength_str = line.split(":")[1].strip()
                            try:
                                wlength = float(wlength_str)
                                logging.info(f"From poni file: wavelength: {wlength * 1e10} Å")
                                wavelength_found = True
                            except ValueError as e:
                                logging.error(f"Error converting wavelength to float: {e}")
                                wlength = None
                            break
                    if not wavelength_found:
                        logging.error("Wavelength not found in poni file.")
                        wlength = None
                except Exception as e:
                    logging.error(f"Cannot open poni file: {e}")
        elif isinstance(self.ai.poni, dict):
            ponif = "\n".join(f"{key}: {value}" for key, value in self.ai.poni.items())
            wavelength_found = False
            try:
                wlength = float(self.ai.poni['wavelength'])
                logging.info(f"From poni file: wavelength: {wlength * 1e10} Å")
                wavelength_found = True
            except ValueError as e:
                logging.error(f"Error converting wavelength to float: {e}")
                wlength = None
            if not wavelength_found:
                logging.error("Wavelength not found in poni dict.")
                wlength = None
        else:
            logging.error("Provided format for poni is wrong.")

        # Now handle data splitting
        if self.ai.azimuth_axis is not None:
            logging.info(f"Creating 1D and 2D data ...")
            # 1D data subentry
            azint1dSE = entry.create_group("azint1d", track_order=True)
            azint1dSE.attrs["NX_class"] = "NXsubentry"

            definition = azint1dSE.create_dataset("definition", data="NXazint1d")
            definition.attrs["type"] = "NX_CHAR"

            azint1dSE["instrument"] = h5py.SoftLink('/entry/instrument')

            reduction = azint1dSE.create_group("reduction", track_order=True)
            reduction.attrs["NX_class"] = "NXprocess"
            prog = reduction.create_dataset("program", data="azint")
            prog.attrs["type"] = "NX_CHAR"
            ver = reduction.create_dataset("version", data=f"azint {azint.__version__}\nNXazint {__version__}")
            ver.attrs["type"] = "NX_CHAR"
            date = reduction.create_dataset("date", data=datetime.now().strftime("%A, %B %d, %Y at %I:%M %p"))
            date.attrs["type"] = "NX_DATE_TIME"
            ref = reduction.create_dataset("reference", data="Jensen, A. B., et al., (2022). J. Synchrotron Rad. 29, 1420-1428.\nhttps://doi.org/10.1107/S1600577522008232,\nhttps://maxiv-science.github.io/azint/")
            ref.attrs["type"] = "NX_CHAR"
            note = reduction.create_dataset("note", data="Geometry convention:\nAzimuthal origin in the horizontal plane to the right of the beam position, i.e., at 3 o’clock,\non the detector face. Positive azimuthal direction: clockwise.")
            note.attrs["type"] = "NX_CHAR"

            input = reduction.create_group("input", track_order=True)
            input.attrs["NX_class"] = "NXparameters"
            dset = input.create_dataset("poni", data=ponif, track_order=True)
            dset.attrs["type"] = "NX_CHAR"
            dset.attrs["filename"] = poni_file if isinstance(self.ai.poni, str) else "Poni dict."

            wavelength = mono.create_dataset("wavelength", data=wlength * 1e10, track_order=True)
            wavelength.attrs["units"] = "angstrom"
            wavelength.attrs["type"] = "NX_FLOAT"
            energy = mono.create_dataset("energy", data=(1.2398 * 1e-9) / wlength, track_order=True)
            energy.attrs["units"] = "keV"
            energy.attrs["type"] = "NX_FLOAT"

            wavelength2 = input.create_dataset("wavelength", data=wlength * 1e10)
            wavelength2.attrs["units"] = "angstrom"
            wavelength2.attrs["type"] = "NX_FLOAT"

            input.create_dataset("n_splitting", data=self.ai.n_splitting)
            input["n_splitting"].attrs["type"] = "NX_NUMBER"
            input.create_dataset("radial_bins", data=self.ai.radial_bins)
            input["radial_bins"].attrs["type"] = "NX_NUMBER"
            input.create_dataset("azimuth_bins", data=1)
            input["azimuth_bins"].attrs["type"] = "NX_NUMBER"
            input.create_dataset("unit", data=self.ai.unit)    
            input["unit"].attrs["type"] = "NX_CHAR"
            input.create_dataset("mask", data=self.ai.mask_path if self.ai.mask_path else ("A numpy array was provided" if self.ai.mask is not None else "None"))
            input["mask"].attrs["type"] = "NX_CHAR"
            
            input.create_dataset("solid_angle", data=True if self.ai.solid_angle else False)
            input["solid_angle"].attrs["type"] = "NX_BOOLEAN"

            polarization = self.ai.polarization_factor if self.ai.polarization_factor is not None else 0
            input.create_dataset("polarization_factor", data=polarization)
            input["polarization_factor"].attrs["type"] = "NX_FLOAT"
            error_model = self.ai.error_model if self.ai.error_model else "None"
            input.create_dataset("error_model", data=error_model)
            input["error_model"].attrs["type"] = "NX_CHAR"


            azint1d = azint1dSE.create_group("data")
            azint1d.attrs["NX_class"] = "NXdata"
            azint1d.attrs["signal"] = "I"
            azint1d.attrs["axes"] = [".", "radial_axis"]
            azint1d.attrs["interpretation"] = "spectrum"
            self.write_radial_axis(azint1d, self.ai.unit, self.ai.radial_axis, self.ai.radial_bins)

            azint2dSE = entry.create_group("azint2d", track_order=True)
            azint2dSE.attrs["NX_class"] = "NXsubentry"

            definition = azint2dSE.create_dataset("definition", data="NXazint2d")
            definition.attrs["type"] = "NX_CHAR"

            azint2dSE["instrument"] = h5py.SoftLink('/entry/instrument')

            reduction = azint2dSE.create_group("reduction", track_order=True)
            reduction.attrs["NX_class"] = "NXprocess"
            prog = reduction.create_dataset("program", data="azint-pipeline")
            prog.attrs["type"] = "NX_CHAR"
            ver = reduction.create_dataset("version", data="azint 1.1.0\nNXazint 0.0.1")
            ver.attrs["type"] = "NX_CHAR"
            date = reduction.create_dataset("date", data=datetime.now().strftime("%A, %B %d, %Y at %I:%M %p"))
            date.attrs["type"] = "NX_DATE_TIME"
            ref = reduction.create_dataset("reference", data="Jensen, A. B., et al., (2022). J. Synchrotron Rad. 29, 1420-1428.\nhttps://doi.org/10.1107/S1600577522008232,\nhttps://maxiv-science.github.io/azint/")
            ref.attrs["type"] = "NX_CHAR"
            note = reduction.create_dataset("note", data="Geometry convention:\nAzimuthal origin in the horizontal plane to the right of the beam position, i.e., at 3 o’clock,\non the detector face. Positive azimuthal direction: clockwise.")
            note.attrs["type"] = "NX_CHAR"

            input = reduction.create_group("input", track_order=True)
            input.attrs["NX_class"] = "NXparameters"

            wavelength2 = input.create_dataset("wavelength", data=wlength * 1e10)
            wavelength2.attrs["units"] = "angstrom"
            wavelength2.attrs["type"] = "NX_FLOAT"

            input.create_dataset("n_splitting", data=self.ai.n_splitting)
            input["n_splitting"].attrs["type"] = "NX_NUMBER"
            input.create_dataset("radial_bins", data=self.ai.radial_bins)
            input["radial_bins"].attrs["type"] = "NX_NUMBER"
            input.create_dataset("azimuth_bins", data=self.ai.azimuth_bins)
            input["azimuth_bins"].attrs["type"] = "NX_NUMBER"
            input.create_dataset("unit", data=self.ai.unit)
            input["unit"].attrs["type"] = "NX_CHAR"
            input.create_dataset("mask", data=self.ai.mask_path if self.ai.mask_path else ("A numpy array was provided" if self.ai.mask is not None else "None"))
            input["mask"].attrs["type"] = "NX_CHAR"
            
            input.create_dataset("solid_angle", data=True if self.ai.solid_angle else False)
            input["solid_angle"].attrs["type"] = "NX_BOOLEAN"

            polarization = self.ai.polarization_factor if self.ai.polarization_factor is not None else 0
            input.create_dataset("polarization_factor", data=polarization)
            input["polarization_factor"].attrs["type"] = "NX_FLOAT"
            error_model = self.ai.error_model if self.ai.error_model else "None"
            input.create_dataset("error_model", data=error_model)
            input["error_model"].attrs["type"] = "NX_CHAR"

            azint2d = azint2dSE.create_group("data")
            azint2d.attrs["NX_class"] = "NXdata"
            azint2d.attrs["signal"] = "I"
            azint2d.attrs["axes"] = [".", "azimuthal_axis", "radial_axis"]
            azint2d.attrs["interpretation"] = "image"
            entry["data"] = h5py.SoftLink('/entry/azint1d/data')
            self.write_radial_axis(azint2d, self.ai.unit, self.ai.radial_axis, self.ai.radial_bins)

            norm = self.ai.norm.reshape(self.ai.output_shape)
            dsetnorm = azint2d.create_dataset("norm", data=norm)
            dsetnorm.attrs["units"] = "arbitrary units"
            dsetnorm.attrs["long_name"] = "normalized intensity"
            dsetnorm.attrs["type"] = "NX_FLOAT"

            dset = azint2d.create_dataset("azimuthal_axis", data=self.ai.azimuth_axis)
            dset.attrs["units"] = "degrees"
            dset.attrs["long_name"] = "Azimuthal bin center"
            dset.attrs["type"] = "NX_FLOAT"

            if isinstance(self.ai.azimuth_bins, Iterable):
                aedges = self.ai.azimuth_bins
            else:
                acentres = self.ai.azimuth_axis
                awidth = acentres[1] - acentres[0]
                aedges = (acentres - 0.5 * awidth)
                aedges = np.append(aedges, aedges[-1] + awidth)

            dset2 = azint2d.create_dataset("azimuthal_axis_edges", data=aedges)
            dset2.attrs["units"] = "degrees"
            dset2.attrs["long_name"] = "Edges of azimuthal bins"
            dset2.attrs["type"] = "NX_FLOAT"

            azint1dSE.attrs["default"] = "data"
            azint2dSE.attrs["default"] = "data"
            entry.attrs["default"] = "data"
            
        else:
            logging.info(f"Creating just 1D data ...")
            # ONLY 1D DATA section
            reduction = entry.create_group("reduction", track_order=True)
            reduction.attrs["NX_class"] = "NXprocess"
            prog = reduction.create_dataset("program", data="azint-pipeline")
            prog.attrs["type"] = "NX_CHAR"
            ver = reduction.create_dataset("version", data=f"azint {azint.__version__}\nNXazint {__version__}")
            ver.attrs["type"] = "NX_CHAR"
            date = reduction.create_dataset("date", data=datetime.now().strftime("%A, %B %d, %Y at %I:%M %p"))
            date.attrs["type"] = "NX_DATE_TIME"
            ref = reduction.create_dataset("reference", data="Jensen, A. B., et al., (2022). J. Synchrotron Rad. 29, 1420-1428.\nhttps://doi.org/10.1107/S1600577522008232,\nhttps://maxiv-science.github.io/azint/")
            ref.attrs["type"] = "NX_CHAR"
            note = reduction.create_dataset("note", data="Geometry convention:\nAzimuthal origin in the horizontal plane to the right of the beam position, i.e., at 3 o’clock,\non the detector face. Positive azimuthal direction: clockwise.")
            note.attrs["type"] = "NX_CHAR"

            input = reduction.create_group("input", track_order=True)
            input.attrs["NX_class"] = "NXparameters"
            dset = input.create_dataset("poni", data=ponif, track_order=True)
            dset.attrs["type"] = "NX_CHAR"
            dset.attrs["filename"] = poni_file
            # Add wavelength and energy to mono
            wavelength = mono.create_dataset("wavelength", data=wlength * 1e10, track_order=True)
            wavelength.attrs["units"] = "angstrom"
            wavelength.attrs["type"] = "NX_FLOAT"
            energy = mono.create_dataset("energy", data=(1.2398 * 1e-9) / wlength, track_order=True)
            energy.attrs["units"] = "keV"
            energy.attrs["type"] = "NX_FLOAT"
        
            # Add other info from poni to input
            wavelength2 = input.create_dataset("wavelength", data=wlength * 1e10)     
            wavelength2.attrs["units"] = "angstrom"
            wavelength2.attrs["type"] = "NX_FLOAT"
            
            input.create_dataset("n_splitting", data=self.ai.n_splitting)
            input["n_splitting"].attrs["type"] = "NX_NUMBER"
            input.create_dataset("radial_bins", data=self.ai.radial_bins)
            input["radial_bins"].attrs["type"] = "NX_NUMBER"
            azimuth_bins = self.ai.azimuth_bins if self.ai.azimuth_bins else 1
            input.create_dataset("azimuth_bins", data=azimuth_bins)
            input["azimuth_bins"].attrs["type"] = "NX_NUMBER"
            input.create_dataset("unit", data=self.ai.unit)
            input["unit"].attrs["type"] = "NX_CHAR"
            input.create_dataset("mask", data=self.ai.mask_path if self.ai.mask_path else ("A numpy array was provided" if self.ai.mask is not None else "None"))
            input["mask"].attrs["type"] = "NX_CHAR"
            
            input.create_dataset("solid_angle", data=True if self.ai.solid_angle else False)
            input["solid_angle"].attrs["type"] = "NX_BOOLEAN"

            polarization = self.ai.polarization_factor if self.ai.polarization_factor is not None else 0
            input.create_dataset("polarization_factor", data=polarization)
            input["polarization_factor"].attrs["type"] = "NX_FLOAT"
            error_model = self.ai.error_model if self.ai.error_model else "None"
            input.create_dataset("error_model", data=error_model)
            input["error_model"].attrs["type"] = "NX_CHAR"
            
            azint1d = entry.create_group("data", track_order=True)
            azint1d.attrs["NX_class"] = "NXdata"
            azint1d.attrs["signal"] = "I"
            azint1d.attrs["axes"] = [".", "radial_axis"]
            azint1d.attrs["interpretation"] = "spectrum"
            self.write_radial_axis(azint1d, self.ai.unit, self.ai.radial_axis, self.ai.radial_bins)

            entry.attrs["default"] = "data"

    
        
    def save_divide(self, a, b):
        return np.divide(a, b, out=np.zeros_like(a), where=b!=0.0)

    def add_data(self, integrated_data):

        if len(integrated_data) == 3:
            normalized = False
            res, errors, norm = integrated_data
        else:
            normalized = True
            res, errors = integrated_data
        
        data = {}
        if res.ndim == 1: # must be radial bins only, no eta, ie 1d.
            if normalized == False:
                I = self.save_divide(res, norm)
            else:
                I = res
            if errors is not None:
                if normalized == False:
                    errors = self.save_divide(errors, norm)
                data["/entry/data/I_errors"] = errors
        else:  # will have eta bins
            I = np.sum(res, axis=0)
            cake = res
            if normalized == False:
                I = self.save_divide(np.sum(res, axis=0), np.sum(norm, axis=0))
                cake = self.save_divide(res, norm)
            data["/entry/azint2d/data/I"] = cake
            if errors is not None:
                if normalized == False:
                    data["/entry/azint2d/data/I_errors"] = self.save_divide(errors, norm)
                    errors = self.save_divide(np.sum(errors, axis=0), np.sum(norm, axis=0))
                else:
                    errors = np.sum(errors, axis=0)

        if self.ai.azimuth_axis is not None:
            data["/entry/azint1d/data/I"] = I
            if errors is not None:
                data["/entry/azint1d/data/I_errors"] = errors
        else:
            data["/entry/data/I"] = I

        with h5py.File(self.output_file, "r+") as fh_u:
            for key, value in data.items():
                new_dset = fh_u.get(key)
                if not new_dset:
                    new_dset = fh_u.create_dataset(key, dtype=value.dtype,
                                                   shape=(0, *value.shape),
                                                   maxshape=(None, *value.shape),
                                                   chunks=(1, *value.shape))
                    # I and I_error created here
                    new_dset.attrs["units"] = "arbitrary units"
                    new_dset.attrs["long_name"] = "intensity"
                    new_dset.attrs["type"] = "NX_FLOAT"
                    if "I_error" in key:
                        new_dset.attrs["units"] = "arbitrary units"
                        new_dset.attrs["long_name"] = "estimated errors on intensity"
                        new_dset.attrs["type"] = "NX_FLOAT"

                n = new_dset.shape[0]
                new_dset.resize(n + 1, axis=0)
                new_dset[n] = value

    def get_bl_name_from_path(self, path, bl_names_enum):
        if not isinstance(path, str):
            return "Unknown"
        for bl_name in bl_names_enum:
            if bl_name.value.lower() in path.lower():
                return bl_name.value
        return "Unknown"

    def write_radial_axis(self, group, unit, radial_axis, radial_bins):
        # real dataset for radial axis is always "radial axis"
        dset = group.create_dataset("radial_axis", data=radial_axis, track_order=True)
        if unit == "q":
            dset.attrs["units"] ="1/angstrom"
            dset.attrs["long_name"] = "q"
            dset.attrs["type"] = "NX_NUMBER"
        else:
            dset.attrs["units"] = "degrees"
            dset.attrs["long_name"] = "tth"
            dset.attrs["type"] = "NX_NUMBER"

        if isinstance(radial_bins, Iterable):
            edges = radial_bins
        else:
            centres = radial_axis
            width = centres[1]-centres[0]
            edges = (centres-0.5*width)
            edges = np.append(edges,edges[-1]+width)

        dsete = group.create_dataset(f"radial_axis_edges", data=edges, track_order=True)
        dsete.attrs["type"] = "NX_FLOAT"
        if unit == "q":
            dsete.attrs["units"] = "1/angstrom"
            dsete.attrs["long_name"] = "Edges of q bins"
            dset.attrs["type"] = "NX_FLOAT"
        else:
            dsete.attrs["units"] = "degrees"
            dsete.attrs["long_name"] = "Edges of tth bins"
            dset.attrs["type"] = "NX_FLOAT"