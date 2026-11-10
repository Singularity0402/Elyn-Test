import json,math
from pathlib import Path
root=Path(__file__).resolve().parent
max_error=0.0
min_gap=float('inf')
for i in range(1,51):
    x=i/51
    for j in range(1,21):
        theta=j*math.pi/20
        s=1-x
        d=math.hypot(math.cos(theta)-x,math.sin(theta))
        error=abs((d*d-s*s)-2*x*(1-math.cos(theta)))
        max_error=max(max_error,error)
        min_gap=min(min_gap,d-s)
        assert d>s
        assert error<1e-12
for x in [0.0,0.25,0.5,0.75,1.0]:
    assert abs(math.hypot(1-x,0)-(1-x))<1e-12
for theta in [0,math.pi/4,math.pi/2,math.pi]:
    assert abs(math.hypot(math.cos(theta),math.sin(theta))-1)<1e-12
out={'status':'PASS_ALGEBRA_ONLY','interior_samples':1000,'L':1,
     'max_identity_error':max_error,'min_positive_length_gap':min_gap,'boundary_cases':9,
     'scope':'Numerical cross-check of a stated idealized geometry, not physical simulation or product validation.'}
(root/'algebra_check.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out))
