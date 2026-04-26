"""Write minimal centroid MS2 mzML from internal spectrum dicts (optional ``psims``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def write_mzml_ms2_file(path: Path | str, spectra: list[dict[str, Any]]) -> None:
    """
    One run, multiple MS2 centroid spectra. Requires ``pip install psims``.

    ``spectra`` items use keys: ``spectrum_id``, ``precursor_mz``, ``precursor_charge``,
    ``peaks_mz``, ``peaks_intensity``; optional ``activation``.
    """
    try:
        import psims.mzml  # type: ignore[import-untyped]
    except ImportError as e:
        raise RuntimeError(
            "mzML export needs the psims package: pip install psims"
        ) from e

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with psims.mzml.MzMLWriter(str(p)) as writer:
        writer.controlled_vocabularies()
        writer.file_description(["MSn spectrum"])
        writer.software_list(
            [
                {
                    "id": "ptagent-ms-formats",
                    "version": "1",
                    "params": ["PTAgent pkg.ms_formats"],
                }
            ]
        )
        writer.instrument_configuration_list(
            [
                writer.InstrumentConfiguration(
                    "ic",
                    [
                        writer.Source(1, ["electrospray ionization"]),
                        writer.Analyzer(2, ["mass analyzer"]),
                        writer.Detector(3, ["detector"]),
                    ],
                    ["unknown instrument"],
                )
            ]
        )
        writer.data_processing_list(
            [
                writer.DataProcessing(
                    [writer.ProcessingMethod(1, "PTAgent export")], id="dp"
                )
            ]
        )
        with writer.run(id=1, instrument_configuration="ic"):
            with writer.spectrum_list(len(spectra)):
                for i, spec in enumerate(spectra):
                    sid = str(spec.get("spectrum_id") or f"scan={i + 1}")
                    precursor = writer.precursor_builder()
                    precursor.selected_ion(
                        mz=float(spec["precursor_mz"]),
                        charge=int(spec["precursor_charge"]),
                    )
                    act = spec.get("activation")
                    if act:
                        precursor.activation({"params": [str(act)]})
                    writer.write_spectrum(
                        list(spec["peaks_mz"]),
                        list(spec["peaks_intensity"]),
                        id=sid,
                        centroided=True,
                        params=[{"ms level": 2}],
                        precursor_information=precursor,
                    )


__all__ = ["write_mzml_ms2_file"]
