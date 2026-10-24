from launcher.qtui.color_science import lab,channels,palette,contrast,readable,tone_color


def test_semantic_palettes_keep_text_readable_for_extreme_seeds():
    for seed in ('#000000','#ffffff','#ff0000','#00ff00','#0000ff','#cebafa','#808080'):
        for mode in ('dark','light'):
            for style in ('fidelity','tonal_spot','vibrant','neutral','fruit_salad','rainbow'):
                colors=palette(seed,mode,style)
                for foreground in ('text','muted','selected_text'):
                    assert contrast(colors[foreground],colors['surface'])>=4.5,(seed,mode,style,foreground)


def test_oklab_roundtrip_and_gamut_mapping():
    import math
    for color in ('#ff0000','#00ff00','#0000ff','#cebafa','#808080'):
        light,a,b=lab(channels(color))
        rebuilt=tone_color(light,math.hypot(a,b),math.atan2(b,a))
        assert max(abs(a-b) for a,b in zip(channels(color),channels(rebuilt)))<.009
    assert contrast(readable('#eeeeee','#ffffff'),'#ffffff')>=4.5


def test_color_styles_produce_distinct_results_and_cache_is_bounded():
    colors={palette('#3f87ab','dark',style)['accent'] for style in
            ('fidelity','tonal_spot','vibrant','neutral','fruit_salad','rainbow')}
    assert len(colors)==6
    for i in range(150):palette('#%06x'%(i*101),'dark','fidelity')
    assert palette.cache_info().currsize<=96
