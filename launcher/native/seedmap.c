/* Onion's small, bounded ABI for unmodified MIT-licensed cubiomes. */
#include "cubiomes/generator.h"
#include "cubiomes/finders.h"
#include "cubiomes/util.h"
#include <stdlib.h>
#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

API int onion_version(const char *version) { return str2mc(version); }

API int onion_biome_at(const char *version, uint64_t seed, int dim, int x, int y, int z) {
    int mc=str2mc(version);
    if (!mc || dim < -1 || dim > 1) return -1;
    Generator *g=malloc(sizeof(Generator));if (!g) return -1;
    setupGenerator(g,mc,0);applySeed(g,dim,seed);
    int biome=getBiomeAt(g,1,x,y,z);free(g);return biome;
}

API int onion_map(const char *version, uint64_t seed, int dim, int x, int z,
                  int scale, int width, int height, int y, unsigned char *rgb, int *ids) {
    int mc = str2mc(version);
    if (!mc || width < 1 || height < 1 || width > 512 || height > 512 ||
        (scale != 1 && scale != 4 && scale != 16 && scale != 64 && scale != 256) || dim < -1 || dim > 1) return -1;
    Generator *g = malloc(sizeof(Generator));
    if (!g) return -2;
    setupGenerator(g, mc, 0); applySeed(g, dim, seed);
    Range r = {scale, x, z, width, height, scale==1 ? y : (int)floor((double)y/4), 1};
    int *cache = allocCache(g, r);
    if (!cache) { free(g); return -2; }
    int err = genBiomes(g, cache, r);
    unsigned char colors[256][3]; initBiomeColors(colors);
    if (!err) for (int i=0;i<width*height;i++) {
        ids[i]=cache[i]; int b=cache[i];
        for (int c=0;c<3;c++) rgb[3*i+c]=(b>=0 && b<256)?colors[b][c]:100;
    }
    free(cache); free(g); return err;
}

API const char *onion_biome_name(const char *version, int id) {
    return biome2str(str2mc(version), id);
}

API int onion_structures(const char *version, uint64_t seed, int dim,
                         int x, int z, int span, int *out, int capacity) {
    int mc=str2mc(version), count=0;
    if (!mc || span<=0 || span>32768 || capacity<0 || capacity>1024) return -1;
    Generator *g=malloc(sizeof(Generator)); if (!g) return -1;
    setupGenerator(g,mc,0);applySeed(g,dim,seed);
    int types[]={Village,Desert_Pyramid,Jungle_Temple,Swamp_Hut,Monument,Mansion,Outpost,
                 Ancient_City,Fortress,Bastion,End_City,Trial_Chambers,Abandoned_Camp};
    for (unsigned t=0;t<sizeof(types)/sizeof(types[0]);t++) {
        StructureConfig cfg;
        if (!getStructureConfig(types[t],mc,&cfg) || cfg.dim!=dim || cfg.regionSize<=0) continue;
        int size=cfg.regionSize*16;
        int ax=(int)floor((double)x/size), az=(int)floor((double)z/size);
        for (int rz=az;rz<=(int)floor((double)(z+span)/size);rz++)
        for (int rx=ax;rx<=(int)floor((double)(x+span)/size);rx++) {
            Pos p;
            if (count>=capacity) {free(g);return count;}
            if (getStructurePos(types[t],mc,seed,rx,rz,&p) && p.x>=x && p.x<x+span &&
                p.z>=z && p.z<z+span && isViableStructurePos(types[t],g,p.x,p.z,0)) {
                out[count*3]=t;out[count*3+1]=p.x;out[count*3+2]=p.z;count++;
            }
        }
    }
    free(g);return count;
}
