import os
import pygame

class MapRenderer:
    def __init__(self, tiles_dir=None, map_name="MyFirstMap"):
        if tiles_dir is None:
            client_dir = os.path.dirname(os.path.abspath(__file__))
            workspace_dir = os.path.abspath(os.path.join(client_dir, "..", "..", ".."))
            tiles_dir = os.path.join(workspace_dir, "res", "images", "tiles")
        self.tiles_dir = tiles_dir
        self.map_name = map_name
        self.tile_size = 32
        self.map_width = 1440
        self.map_height = 1080
        
        self.ground_layer = []
        self.building_layer = []
        self.object_layer = []
        self.collision_layer = []
        
        self.tile_cache = {}
        
        self.load_layers()

    def load_layer(self, suffix):
        path = os.path.join(self.tiles_dir, f"{self.map_name}-{suffix}-p.json")
        if not os.path.exists(path):
            print(f"Warning: Layer file not found: {path}")
            return [0] * (self.map_width * self.map_height)
            
        with open(path, "r") as f:
            text = f.read()
        return [int(x.strip()) for x in text.split(",") if x.strip()]

    def load_layers(self):
        print("Loading map layers into memory...")
        self.ground_layer = self.load_layer("ground")
        self.building_layer = self.load_layer("building")
        self.object_layer = self.load_layer("object")
        self.collision_layer = self.load_layer("collision")
        print("Map layers loaded successfully.")

    def is_solid(self, tile_x, tile_y):
        if tile_x < 0 or tile_x >= self.map_width or tile_y < 0 or tile_y >= self.map_height:
            return True
        idx = int(tile_y) * self.map_width + int(tile_x)
        if idx >= len(self.collision_layer):
            return True
        # 1 (walls), 2 (trees/objects), 11 (solid pillars/roofs) are blocking.
        # 0 (ground) and 3 (safe zone) are walkable.
        return self.collision_layer[idx] in [1, 2, 11]

    def get_tile_image(self, tile_id):
        if tile_id == 0:
            return None
        
        if tile_id not in self.tile_cache:
            path = os.path.join(self.tiles_dir, f"{tile_id}.png")
            if os.path.exists(path):
                try:
                    # Load and convert to support alpha transparency in Pygame
                    img = pygame.image.load(path).convert_alpha()
                    self.tile_cache[tile_id] = img
                except Exception as e:
                    print(f"Error loading tile {tile_id}: {e}")
                    self.tile_cache[tile_id] = None
            else:
                self.tile_cache[tile_id] = None
                
        return self.tile_cache[tile_id]

    def render(self, surface, camera_x, camera_y, screen_width, screen_height):
        """
        Renders the visible portion of the map.
        camera_x and camera_y are the player's tile coordinates.
        """
        # Calculate how many tiles fit on the screen
        tiles_x = (screen_width // self.tile_size) + 2
        tiles_y = (screen_height // self.tile_size) + 2
        
        # Center of the screen in tiles
        center_tile_x = screen_width // (2 * self.tile_size)
        center_tile_y = screen_height // (2 * self.tile_size)
        
        # Starting tile coordinates to render (top-left of screen)
        start_tile_x = max(0, int(camera_x - center_tile_x))
        start_tile_y = max(0, int(camera_y - center_tile_y))
        
        end_tile_x = min(self.map_width, start_tile_x + tiles_x)
        end_tile_y = min(self.map_height, start_tile_y + tiles_y)
        
        # Calculate pixel offset to smoothly center the camera
        offset_x = int((camera_x - start_tile_x) * self.tile_size - (screen_width / 2))
        offset_y = int((camera_y - start_tile_y) * self.tile_size - (screen_height / 2))

        # Render visible tiles layer by layer
        for y in range(start_tile_y, end_tile_y):
            for x in range(start_tile_x, end_tile_x):
                idx = y * self.map_width + x
                
                # Screen position to draw this tile
                screen_x = (x - start_tile_x) * self.tile_size - offset_x
                screen_y = (y - start_tile_y) * self.tile_size - offset_y
                
                # 1. Ground Layer
                g_val = self.ground_layer[idx]
                g_img = self.get_tile_image(g_val)
                if g_img:
                    surface.blit(g_img, (screen_x, screen_y))
                    
                # 2. Building Layer
                b_val = self.building_layer[idx]
                b_img = self.get_tile_image(b_val)
                if b_img:
                    surface.blit(b_img, (screen_x, screen_y))
                    
                # 3. Object Layer
                o_val = self.object_layer[idx]
                o_img = self.get_tile_image(o_val)
                if o_img:
                    surface.blit(o_img, (screen_x, screen_y))
