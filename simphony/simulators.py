# Copyright © Simphony Project Contributors
# Licensed under the terms of the MIT License
# (see simphony/__init__.py for details)

from typing import Literal, Optional, Tuple

import numpy as np

from simphony import Model
from simphony.models import Subcircuit
from simphony.pins import PinList
from simphony.tools import freq2wl, wl2freq


class Simulator(Model):
    pins = ("input", "output")

    def _generate(
        self,
        freqs: np.array,
        s_parameters_method: Literal[
            "monte_carlo_s_parameters", "s_parameters"
        ] = "s_parameters",
    ) -> Tuple[np.ndarray, PinList]:
        """Generates the scattering parameters for the circuit.

        This method gets the scattering parameters for the circuit and
        returns them with the list of corresponding pins.
        """
        if (
            not self.pins["input"]._isconnected()
            or not self.pins["output"]._isconnected()
        ):
            raise RuntimeError("Simulator must be connected before simulating.")

        subcircuit = self.circuit.to_subcircuit(permanent=False)
        s_params = getattr(subcircuit, s_parameters_method)(freqs)

        return (s_params, subcircuit.pins)

    def simulate(
        self,
        *,
        dB: bool = False,
        freq: float = 0,
        freqs: Optional[np.array] = None,
        s_parameters_method: Literal[
            "monte_carlo_s_parameters", "s_parameters"
        ] = "s_parameters"
    ) -> Tuple[np.array, np.array]:
        """Simulates the circuit.

        Returns the power ratio at each specified frequency.

        Parameters
        ----------
        dB :
            Returns the power ratios in deciBels when True.
        freq :
            The single frequency to run the simulation for. Must be set if freqs
            is not.
        freqs :
            The list of frequencies to run simulations for. Must be set if freq
            is not.
        s_parameters_method :
            The method name to call to get the scattering parameters.
        """
        if freq:
            freqs = np.array(freq)

        s_params, pins = self._generate(freqs, s_parameters_method)
        power_ratios = np.abs(s_params.copy()) ** 2

        if dB:
            power_ratios = np.log10(power_ratios)

        input = pins.index(self.pins["input"]._connection)
        output = pins.index(self.pins["output"]._connection)

        return (freqs, power_ratios[:, input, output])


class SweepSimulator(Simulator):
    """Wrapper simulator to make it easier to simulate over a range of
    frequencies."""

    def __init__(
        self, start: float = 1.5e-6, stop: float = 1.6e-6, num: int = 2000
    ) -> None:
        """Initializes the SweepSimulator instance.

        The start and stop values can be given in either wavelength or
        frequency. The simulation will output results in the same mode.

        Parameters
        ----------
        start :
            The starting frequency/wavelength.
        stop :
            The stopping frequency/wavelength.
        num :
            The number of points between start and stop.
        """
        super().__init__()

        # automatically detect mode
        self.mode = "wl" if start < 1 else "freq"

        # if mode is wavelength, convert to frequencies
        if self.mode == "wl":
            start = wl2freq(start)
            stop = wl2freq(stop)

        self.freqs = np.linspace(start, stop, num)

    def simulate(self, **kwargs) -> Tuple[np.array, np.array]:
        """Runs the sweep simulation for the circuit."""
        freqs, power_ratios = super().simulate(**kwargs, freqs=self.freqs)

        if self.mode == "wl":
            return (freq2wl(freqs), np.flip(power_ratios))

        return (freqs, power_ratios)


class MonteCarloSweepSimulator(SweepSimulator):
    def simulate(self, runs: int = 10, **kwargs) -> Tuple[np.array, np.array]:
        """Runs the Monte Carlo sweep simulation for the circuit.

        Parameters
        ----------
        runs :
            The number of Monte Carlo iterations to run (default 10).
        """
        results = []

        for i in range(runs):
            # use s_parameters for the first run, then monte_carlo_* for the rest
            s_parameters_method = "monte_carlo_s_parameters" if i else "s_parameters"
            results.append(
                super().simulate(**kwargs, s_parameters_method=s_parameters_method)
            )

            for component in self.circuit:
                component.regenerate_monte_carlo_parameters()

        return results
