"""Map gestures, negative world coordinates, seam-free planning and real LoD."""
import math
from launcher.map_view import Viewport,tile_cells,biome_name,biome_color
from launcher.seedmap import generate,library,VERSIONS,structure_positions


def test_cursor_anchored_zoom_and_pan_are_reversible():
    view=Viewport(-1420,1900,4)
    anchor=view.world(107,280,960,540)
    for scale in (2.5,1,.125,16,256,4):
        view.zoom_at(scale,107,280,960,540)
        assert all(math.isclose(a,b,abs_tol=1e-8) for a,b in zip(anchor,view.world(107,280,960,540)))
    x,z=view.x,view.z;view.pan(100,-83);view.pan(-100,83)
    assert math.isclose(view.x,x) and math.isclose(view.z,z)
    point=view.screen(*anchor,960,540)
    assert all(math.isclose(a,b,abs_tol=1e-8) for a,b in zip(point,(107,280)))


def test_tile_planning_covers_rectangular_view_without_negative_seams():
    for center in (-1024,-.5,0,1023.9):
        for bpp in (.125,1,3.99,4,64,256):
            view=Viewport(center,-center,bpp);scale,cells=tile_cells(view,1920,720);span=scale*256
            assert 0<len(cells)<=48 and all(x%span==z%span==0 for x,z in cells)
            left,top,right,bottom=view.bounds(1920,720)
            for px,pz in ((left,top),(right-.001,top),(left,bottom-.001),(right-.001,bottom-.001),(view.x,view.z)):
                assert (math.floor(px/span)*span,math.floor(pz/span)*span) in cells
            distances=[(x+span/2-view.x)**2+(z+span/2-view.z)**2 for x,z in cells]
            assert distances==sorted(distances)


def test_actual_native_levels_and_block_height_agree():
    native=library()
    for version in VERSIONS:
        for dimension in (-1,0,1):
            for scale in (1,256):
                data=generate(123,version,dimension,x=-268,z=-444,y=-16,scale=scale,size=16,structures=False)
                assert len(data.ids)==256 and set(data.ids)<=data.legend.keys()
    block=generate(0,'26.2',x=-268,z=-444,y=-16,scale=1,size=16,structures=False)
    # At block resolution the Voronoi lookup can differ from its quart cell.
    assert block.ids[8*16+8]==native.onion_biome_at(b'26.2',0,0,-268,-16,-444)
    block=generate(-3829811542736183482,'26.3',x=68148,z=80990,y=77,scale=1,size=16,structures=False)
    assert block.ids[8*16+8]==native.onion_biome_at(b'26.3',-3829811542736183482,0,68148,77,80990)==188
    assert biome_name('sulfur_caves')=='硫磺洞穴' and len(biome_color('sulfur_caves'))==3


def test_structure_query_is_independent_of_biome_raster():
    data=generate(123,'26.3',x=512,z=512,scale=4,size=256,structures=True)
    assert data.structures==structure_positions(123,'26.3',0,*data.origin,1024)
