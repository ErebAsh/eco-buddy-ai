"""
Ocean Surface Fluid Dynamics Engine.
Models U (zonal/East-West) and V (meridional/North-South) ocean surface currents
using simplified wind-driven Ekman transport and Coriolis force.
"""

import numpy as np
import math
from typing import Tuple
from plugins.ocean_current.world_map import WorldMapGrid

class OceanCurrentSolver:
    def __init__(self, grid: WorldMapGrid):
        self.grid = grid
        
        # Current velocities in meters per second
        self.u_velocity = np.zeros((self.grid.rows, self.grid.cols))
        self.v_velocity = np.zeros((self.grid.rows, self.grid.cols))
        
        self.omega = 7.2921e-5 # Earth's angular velocity
        self._initialize_major_currents()
        
    def _initialize_major_currents(self):
        """
        Creates static underlying major ocean gyres and boundary currents
        like the Gulf Stream, Kuroshio, and Antarctic Circumpolar Current.
        """
        for r in range(self.grid.rows):
            for c in range(self.grid.cols):
                if self.grid.land_mask[r, c] == 0:
                    continue
                    
                lat, lon = self.grid.get_lat_lon(r, c)
                
                # Antarctic Circumpolar Current (Massive eastward flow)
                if lat < -50 and lat > -70:
                    self.u_velocity[r, c] = 1.2 # Fast east
                    self.v_velocity[r, c] = 0.1
                    
                # Equatorial Currents (Westward)
                elif -15 < lat < 15:
                    self.u_velocity[r, c] = -0.5
                    
                # Gulf Stream (North-East along US coast)
                elif 20 < lat < 45 and -80 < lon < -40:
                    # Accelerate as it moves north
                    self.u_velocity[r, c] = 0.8
                    self.v_velocity[r, c] = 1.0
                    
                # Kuroshio Current (North-East off Japan)
                elif 20 < lat < 40 and 120 < lon < 160:
                    self.u_velocity[r, c] = 0.7
                    self.v_velocity[r, c] = 0.9
                    
                # Subtropical Gyres (Clockwise in N. Hemisphere, Counter in S. Hemisphere)
                elif 15 <= lat <= 45: # North Pacific / Atlantic
                    # Simplified vortex math
                    if lon < 0: # Atlantic
                        cx, cy = -40, 30
                    else: # Pacific
                        cx, cy = 160, 30
                        
                    dx = lon - cx
                    dy = lat - cy
                    dist = math.sqrt(dx**2 + dy**2)
                    if 0 < dist < 30:
                        # Tangential velocity
                        speed = 0.5 * (1.0 - (dist / 30.0))
                        # Clockwise cross product
                        self.u_velocity[r, c] = speed * dy
                        self.v_velocity[r, c] = speed * -dx
                        
                elif -45 <= lat <= -15: # South Pacific / Atlantic
                    if lon < 0:
                        cx, cy = -20, -30
                    else:
                        cx, cy = -120, -30
                        
                    dx = lon - cx
                    dy = lat - cy
                    dist = math.sqrt(dx**2 + dy**2)
                    if 0 < dist < 30:
                        speed = 0.5 * (1.0 - (dist / 30.0))
                        # Counter-clockwise cross product
                        self.u_velocity[r, c] = speed * -dy
                        self.v_velocity[r, c] = speed * dx

    def get_coriolis_parameter(self, lat: float) -> float:
        """ f = 2 * Omega * sin(lat) """
        return 2 * self.omega * math.sin(math.radians(lat))
        
    def step_simulation(self, dt_seconds: float):
        """
        Advances the fluid dynamics by one time step.
        (For this simulator, we assume relatively steady-state macro currents,
        but we allow for slight diffusion and wind perturbation).
        """
        u_new = np.copy(self.u_velocity)
        v_new = np.copy(self.v_velocity)
        
        # Simple diffusion to smooth out the currents
        diffusion_coeff = 0.1
        
        for r in range(1, self.grid.rows - 1):
            for c in range(1, self.grid.cols - 1):
                if self.grid.land_mask[r, c] == 0:
                    continue
                    
                # Laplacian
                u_lap = (self.u_velocity[r+1, c] + self.u_velocity[r-1, c] + 
                         self.u_velocity[r, c+1] + self.u_velocity[r, c-1] - 
                         4 * self.u_velocity[r, c])
                         
                v_lap = (self.v_velocity[r+1, c] + self.v_velocity[r-1, c] + 
                         self.v_velocity[r, c+1] + self.v_velocity[r, c-1] - 
                         4 * self.v_velocity[r, c])
                         
                # Coriolis perturbation (Ekman spiral effect from wind)
                lat, _ = self.grid.get_lat_lon(r, c)
                f = self.get_coriolis_parameter(lat)
                
                # Simplified momentum equations
                u_new[r, c] += (diffusion_coeff * u_lap + f * self.v_velocity[r, c]) * dt_seconds
                v_new[r, c] += (diffusion_coeff * v_lap - f * self.u_velocity[r, c]) * dt_seconds
                
        # Zero out land
        self.u_velocity = u_new * self.grid.land_mask
        self.v_velocity = v_new * self.grid.land_mask
        
    def get_velocity(self, lat: float, lon: float) -> Tuple[float, float]:
        """Returns (U, V) in meters per second."""
        r, c = self.grid.get_indices(lat, lon)
        return self.u_velocity[r, c], self.v_velocity[r, c]
