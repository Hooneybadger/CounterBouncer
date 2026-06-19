"""gurobi vs CP-SAT 코어 스케줄 솔브 비교 (v1.2.0 프런티어 probe).

질문: relax-repair가 CP-SAT로 못 푸는 하드 코어(prob_27 60블록 90s+)를 gurobi(이제 캡 제거)가
더 빨리/좋게 푸나? 풀면 그 인스턴스도 relax win → breadth. 같은 bbox+스케줄 모델을 두 솔버로.
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from relax_repair import _bbox_orients  # noqa: E402


def core(prob, n):
    blocks = prob["blocks"]
    order = sorted(range(len(blocks)), key=lambda i: (blocks[i]["release_time"], blocks[i]["due_date"]))
    sel = order[:n]
    return prob["bays"], [(i, dict(r=int(blocks[i]["release_time"]), p=int(blocks[i]["processing_time"]),
                                   due=int(blocks[i]["due_date"]), orients=_bbox_orients(blocks[i]))) for i in sel]


def solve_cpsat(bays, sub, tcap, workers):
    from ortools.sat.python import cp_model
    nb = len(bays); m = cp_model.CpModel()
    H = max(max(j["due"] for _, j in sub), max(j["r"] for _, j in sub)) + sum(j["p"] for _, j in sub)
    B = {}
    for g, j in sub:
        e = m.NewIntVar(j["r"], H, ""); x = m.NewIntVar(j["r"], H + j["p"], ""); m.Add(x == e + j["p"])
        t = m.NewIntVar(0, H, ""); m.Add(t >= x - j["due"]); opts = []
        for b in range(nb):
            for (w, h) in j["orients"]:
                if w > bays[b]["width"] or h > bays[b]["height"]: continue
                lit = m.NewBoolVar(""); px = m.NewIntVar(0, bays[b]["width"]-w, ""); py = m.NewIntVar(0, bays[b]["height"]-h, "")
                opts.append(dict(lit=lit, bay=b, w=w, h=h, px=px, py=py))
        if not opts: return None
        m.AddExactlyOne([o["lit"] for o in opts])
        X=m.NewIntVar(0,max(by["width"] for by in bays),""); Y=m.NewIntVar(0,max(by["height"] for by in bays),"")
        W=m.NewIntVar(1,max(o["w"] for o in opts),""); Hh=m.NewIntVar(1,max(o["h"] for o in opts),""); Bv=m.NewIntVar(0,max(o["bay"] for o in opts),"")
        for o in opts:
            for var,val in ((X,o["px"]),(Y,o["py"]),(W,o["w"]),(Hh,o["h"]),(Bv,o["bay"])): m.Add(var==val).OnlyEnforceIf(o["lit"])
        B[g]=dict(e=e,x=x,t=t,X=X,Y=Y,W=W,H=Hh,Bv=Bv)
    gids=[g for g,_ in sub]
    for a in range(len(gids)):
        for c in range(a+1,len(gids)):
            i,k=gids[a],gids[c]; bi,bk=B[i],B[k]; sb=m.NewBoolVar("")
            m.Add(bi["Bv"]==bk["Bv"]).OnlyEnforceIf(sb); m.Add(bi["Bv"]!=bk["Bv"]).OnlyEnforceIf(sb.Not())
            s=[m.NewBoolVar("") for _ in range(6)]
            m.Add(bi["x"]<=bk["e"]).OnlyEnforceIf(s[0]); m.Add(bk["x"]<=bi["e"]).OnlyEnforceIf(s[1])
            m.Add(bi["X"]+bi["W"]<=bk["X"]).OnlyEnforceIf(s[2]); m.Add(bk["X"]+bk["W"]<=bi["X"]).OnlyEnforceIf(s[3])
            m.Add(bi["Y"]+bi["H"]<=bk["Y"]).OnlyEnforceIf(s[4]); m.Add(bk["Y"]+bk["H"]<=bi["Y"]).OnlyEnforceIf(s[5])
            m.AddBoolOr(s).OnlyEnforceIf(sb)
    m.Minimize(sum(B[g]["t"] for g in gids))
    sv=cp_model.CpSolver(); sv.parameters.max_time_in_seconds=float(tcap); sv.parameters.num_workers=workers
    t0=time.time(); st=sv.Solve(m); el=time.time()-t0
    return dict(status=sv.StatusName(st), obj=sv.ObjectiveValue() if st in (cp_model.OPTIMAL,cp_model.FEASIBLE) else None,
                bound=sv.BestObjectiveBound(), proven=st==cp_model.OPTIMAL, el=el)


def solve_gurobi(bays, sub, tcap, threads):
    import gurobipy as gp
    from gurobipy import GRB
    nb=len(bays); m=gp.Model(); m.setParam("OutputFlag",0); m.setParam("TimeLimit",float(tcap)); m.setParam("Threads",threads)
    H=max(max(j["due"] for _,j in sub), max(j["r"] for _,j in sub))+sum(j["p"] for _,j in sub)
    B={}
    for g,j in sub:
        e=m.addVar(lb=j["r"],ub=H); x=m.addVar(lb=j["r"],ub=H+j["p"]); m.addConstr(x==e+j["p"])
        t=m.addVar(lb=0,ub=H); m.addConstr(t>=x-j["due"]); opts=[]
        for b in range(nb):
            for (w,h) in j["orients"]:
                if w>bays[b]["width"] or h>bays[b]["height"]: continue
                opts.append(dict(lit=m.addVar(vtype=GRB.BINARY),bay=b,w=w,h=h))
        if not opts: return None
        m.addConstr(gp.quicksum(o["lit"] for o in opts)==1)
        X=m.addVar(lb=0,ub=max(by["width"] for by in bays)); Y=m.addVar(lb=0,ub=max(by["height"] for by in bays))
        W=m.addVar(lb=1,ub=max(o["w"] for o in opts)); Hh=m.addVar(lb=1,ub=max(o["h"] for o in opts))
        litsum={}  # bay -> 그 베이의 lit 합 (정확히 0/1)
        for o in opts:
            litsum[o["bay"]]=litsum.get(o["bay"],0)+o["lit"]
            # lit 활성 시 W/H = 방향, 위치는 활성 베이 안 (indicator)
            m.addGenConstrIndicator(o["lit"],True,W==o["w"]); m.addGenConstrIndicator(o["lit"],True,Hh==o["h"])
            m.addGenConstrIndicator(o["lit"],True,X<=bays[o["bay"]]["width"]-o["w"])
            m.addGenConstrIndicator(o["lit"],True,Y<=bays[o["bay"]]["height"]-o["h"])
        B[g]=dict(e=e,x=x,t=t,X=X,Y=Y,W=W,H=Hh,litsum=litsum)
    gids=[g for g,_ in sub]
    Mt=H+max(j["p"] for _,j in sub)          # 시간 빅엠 (타이트)
    Mx=max(by["width"] for by in bays)        # X 빅엠
    My=max(by["height"] for by in bays)       # Y 빅엠
    for a in range(len(gids)):
        for c in range(a+1,len(gids)):
            i,k=gids[a],gids[c]; bi,bk=B[i],B[k]
            s=[m.addVar(vtype=GRB.BINARY) for _ in range(6)]
            # 분리 빅엠 (단방향: s 활성 시 그 분리 성립), 타입별 타이트 M
            m.addConstr(bi["x"]<=bk["e"]+Mt*(1-s[0])); m.addConstr(bk["x"]<=bi["e"]+Mt*(1-s[1]))
            m.addConstr(bi["X"]+bi["W"]<=bk["X"]+Mx*(1-s[2])); m.addConstr(bk["X"]+bk["W"]<=bi["X"]+Mx*(1-s[3]))
            m.addConstr(bi["Y"]+bi["H"]<=bk["Y"]+My*(1-s[4])); m.addConstr(bk["Y"]+bk["H"]<=bi["Y"]+My*(1-s[5]))
            # ★정확한 same-bay: 같은 베이 b에 둘 다 있으면(litsum 둘 다 1) 분리 최소 1개 강제
            for b in set(bi["litsum"]) & set(bk["litsum"]):
                m.addConstr(gp.quicksum(s) >= bi["litsum"][b] + bk["litsum"][b] - 1)
    m.setObjective(gp.quicksum(B[g]["t"] for g in gids), GRB.MINIMIZE)
    t0=time.time(); m.optimize(); el=time.time()-t0
    st={GRB.OPTIMAL:"OPTIMAL",GRB.TIME_LIMIT:"TIME_LIMIT",GRB.INFEASIBLE:"INFEAS"}.get(m.status,str(m.status))
    obj=m.objVal if m.SolCount>0 else None
    return dict(status=st, obj=obj, bound=m.ObjBound if m.SolCount>0 else None, proven=m.status==GRB.OPTIMAL, el=el)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("inst"); ap.add_argument("-n",type=int,default=60)
    ap.add_argument("-t",type=float,default=20.0); ap.add_argument("-w",type=int,default=4)
    a=ap.parse_args()
    prob=json.load(open(os.path.join(os.path.dirname(__file__),"..","train",f"{a.inst}.json")))
    bays,sub=core(prob,a.n)
    print(f"{a.inst} core N={len(sub)} cap={a.t}s")
    cp=solve_cpsat(bays,sub,a.t,a.w)
    print(f"  CP-SAT : status={cp['status']:9} obj={cp['obj']} bound={cp['bound']:.0f} proven={cp['proven']} {cp['el']:.1f}s")
    gu=solve_gurobi(bays,sub,a.t,a.w)
    print(f"  gurobi : status={gu['status']:9} obj={gu['obj']} bound={gu['bound']} proven={gu['proven']} {gu['el']:.1f}s")


if __name__=="__main__":
    main()
