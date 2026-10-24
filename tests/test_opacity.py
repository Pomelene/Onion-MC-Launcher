from launcher.qtui.opacity import opacity,alpha_byte,qss_color,parse_source_color


def test_opacity_is_linear_and_bounded():
    assert opacity(0)==1 and opacity(100)==0
    assert opacity(150,90)==.1 or abs(opacity(150,90)-.1)<1e-12
    assert opacity(float('nan'))==1 and opacity('bad')==1
    values=[alpha_byte(7/255*opacity(value,90)) for value in range(91)]
    assert values==sorted(values,reverse=True)
    assert values[78:81]==[2,1,1]


def test_qss_alpha_one_byte_never_becomes_opaque_integer_one():
    for byte in range(256):
        value=qss_color((187,221,221),byte/255)
        rgb,ratio=parse_source_color(value)
        assert rgb==(187,221,221) and abs(ratio-byte/255)<1e-8
        assert len(value)==9 and int(value[1:3],16)==byte
