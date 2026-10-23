"""Map projection and tile planning, independent of Qt and world generation."""
import math
from dataclasses import dataclass

NATIVE_SCALES=(1,4,16,64,256)
WORLD_LIMIT=29_000_000


@dataclass
class Viewport:
    x: float=0
    z: float=0
    blocks_per_pixel: float=4

    def world(self,sx,sy,width,height):
        return self.x+(sx-width/2)*self.blocks_per_pixel,self.z+(sy-height/2)*self.blocks_per_pixel

    def screen(self,x,z,width,height):
        return (x-self.x)/self.blocks_per_pixel+width/2,(z-self.z)/self.blocks_per_pixel+height/2

    def pan(self,dx,dy):
        self.x=max(-WORLD_LIMIT,min(WORLD_LIMIT,self.x-dx*self.blocks_per_pixel))
        self.z=max(-WORLD_LIMIT,min(WORLD_LIMIT,self.z-dy*self.blocks_per_pixel))

    def zoom_at(self,bpp,sx,sy,width,height):
        anchor=self.world(sx,sy,width,height)
        self.blocks_per_pixel=max(.125,min(256,float(bpp)))
        self.x=max(-WORLD_LIMIT,min(WORLD_LIMIT,anchor[0]-(sx-width/2)*self.blocks_per_pixel))
        self.z=max(-WORLD_LIMIT,min(WORLD_LIMIT,anchor[1]-(sy-height/2)*self.blocks_per_pixel))

    def bounds(self,width,height):
        return (*self.world(0,0,width,height),*self.world(width,height,width,height))


def tile_cells(view,width,height):
    scale=next((value for value in NATIVE_SCALES if value>=view.blocks_per_pixel),256)
    bounds=view.bounds(width,height)
    while True:
        span=scale*256
        cells=[(x*span,z*span) for z in range(math.floor(bounds[1]/span),math.ceil(bounds[3]/span))
               for x in range(math.floor(bounds[0]/span),math.ceil(bounds[2]/span))]
        if len(cells)<=48 or scale==256:break
        scale*=4
    cells.sort(key=lambda point:(point[0]+span/2-view.x)**2+(point[1]+span/2-view.z)**2)
    return scale,cells


BIOME_NAMES={
 'ocean':'海洋','deep_ocean':'深海','warm_ocean':'暖水海洋','lukewarm_ocean':'温水海洋',
 'cold_ocean':'冷水海洋','frozen_ocean':'冻洋','deep_lukewarm_ocean':'温水深海',
 'deep_cold_ocean':'冷水深海','deep_frozen_ocean':'冰冻深海','river':'河流','frozen_river':'冻河',
 'plains':'平原','sunflower_plains':'向日葵平原','forest':'森林','flower_forest':'繁花森林',
 'birch_forest':'白桦林','old_growth_birch_forest':'原始白桦林','dark_forest':'黑森林',
 'taiga':'针叶林','old_growth_pine_taiga':'原始松木针叶林','old_growth_spruce_taiga':'原始云杉针叶林',
 'snowy_taiga':'积雪针叶林','swamp':'沼泽','mangrove_swamp':'红树林沼泽','jungle':'丛林',
 'bamboo_jungle':'竹林','sparse_jungle':'稀疏丛林','savanna':'热带草原','savanna_plateau':'热带高原',
 'windswept_savanna':'风蚀热带草原','desert':'沙漠','badlands':'恶地','wooded_badlands':'疏林恶地',
 'eroded_badlands':'风蚀恶地','beach':'沙滩','snowy_beach':'积雪沙滩','stony_shore':'石岸',
 'mountains':'山地','windswept_hills':'风袭丘陵','windswept_forest':'风袭森林',
 'windswept_gravelly_hills':'风袭砂砾丘陵','snowy_plains':'雪原','snowy_tundra':'雪原','ice_spikes':'冰刺之地',
 'meadow':'草甸','grove':'雪林','snowy_slopes':'积雪山坡','frozen_peaks':'冰封山峰',
 'jagged_peaks':'尖峭山峰','stony_peaks':'裸岩山峰','mushroom_fields':'蘑菇岛',
 'lush_caves':'繁茂洞穴','dripstone_caves':'溶洞','deep_dark':'深暗之域','cherry_grove':'樱花树林',
 'pale_garden':'苍白之园','sulfur_caves':'硫磺洞穴','dappled_forest':'斑驳森林',
 'nether_wastes':'下界荒地','crimson_forest':'绯红森林','warped_forest':'诡异森林',
 'soul_sand_valley':'灵魂沙峡谷','basalt_deltas':'玄武岩三角洲','the_end':'末地',
 'end_highlands':'末地高地','end_midlands':'末地中地','end_barrens':'末地荒岛','small_end_islands':'末地小型岛屿',
}


def biome_name(name):return BIOME_NAMES.get(name,name.replace('_',' '))


def biome_color(name):
    colors={
     'ocean':'537e9b','deep_ocean':'355d7c','warm_ocean':'61a9b4','lukewarm_ocean':'6099ad',
     'cold_ocean':'587b9b','frozen_ocean':'9ebac9','deep_lukewarm_ocean':'45748c',
     'deep_cold_ocean':'3c5c7d','deep_frozen_ocean':'7a9eb6','river':'6a9cbb','frozen_river':'b7d0db',
     'plains':'a7bd85','sunflower_plains':'b9c78c','forest':'658c67','flower_forest':'8eaa7c',
     'birch_forest':'88a47a','old_growth_birch_forest':'7b9673','dark_forest':'426451',
     'taiga':'779082','old_growth_pine_taiga':'758778','old_growth_spruce_taiga':'62796e',
     'snowy_taiga':'b5c9c4','swamp':'6e8069','mangrove_swamp':'5b7665','jungle':'6b9661',
     'bamboo_jungle':'7eaa6c','sparse_jungle':'92b17b','savanna':'c1bd85','savanna_plateau':'aba873',
     'windswept_savanna':'a6aa85','desert':'e2d1a5','badlands':'bf916b','wooded_badlands':'a5906b',
     'eroded_badlands':'cc9b7d','beach':'e3d6b0','snowy_beach':'d7ded6','stony_shore':'9eaaa1',
     'windswept_hills':'9aa08b','mountains':'9aa08b','windswept_forest':'7a9174',
     'windswept_gravelly_hills':'a7a79d','snowy_plains':'dce4df','snowy_tundra':'dce4df','ice_spikes':'b7d4df',
     'meadow':'abc293','grove':'bfcec3','snowy_slopes':'d8dedb','frozen_peaks':'c2d3d9',
     'jagged_peaks':'b9c2bf','stony_peaks':'b0afa1','mushroom_fields':'b59cae',
     'lush_caves':'749979','dripstone_caves':'ae9685','deep_dark':'425967','cherry_grove':'d7b1bd',
     'pale_garden':'acb7ae','sulfur_caves':'c5bc7d','dappled_forest':'b7a570',
     'nether_wastes':'9c6b65','crimson_forest':'8b565e','warped_forest':'588985','soul_sand_valley':'9d8c7a',
     'basalt_deltas':'797d7e','the_end':'d1caa2','end_highlands':'cac39b','end_midlands':'b7b392',
     'end_barrens':'999886','small_end_islands':'c2bf9e',
    }
    return bytes.fromhex(colors.get(name,'9aa58d'))
