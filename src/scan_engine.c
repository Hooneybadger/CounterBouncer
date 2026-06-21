/* scan.c -- C scan constructor (Python constructor.py 포팅).
 * Python이 ir.masks()로 래스터화해 마샬링(marshal.py)한 바이너리를 읽어 EDD+scan+크레인
 * +occupancy로 construct하고 placement를 바이너리로 출력. 모든 비트연산은 raster_engine의
 * upper-map AND(_overlap_any)와 동일. feasibility는 셀 경계 + 크레인으로 보장(검증기가 최종 확인).
 * 정적 빌드(self-contained)라 서버서 의존성 0. 실패 시 비-0 종료 -> Python floor 폴백. */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <time.h>

#define MAGIC 0x5343414E

static int WORDS, N_BAYS, N_BLOCKS, MAX_LAY;
static double W1, W2, W3;

typedef struct { int my0, mx0, h; uint64_t *rows; } Layer; /* rows: h*WORDS */
typedef struct { int n_layers; Layer *lay;
                 int min_cx, max_cx, min_cy, max_cy; /* 정수 셀 bbox(참고) */
                 double r0,r1,r2,r3; } Orient;        /* rel_bbox(float, 경계=Python 일치) */
typedef struct { int release, proc, due; double workload; double *prefs;
                 int n_orient; Orient *or_; } Block;
typedef struct { int W, H; } Bay;

static Bay *bays;
static Block *blocks;
static int *ORDERS;  /* M개 구성 순서(평탄, M*N_BLOCKS) -- 배치 순서 포트폴리오 */
static int N_ORD;    /* 순서 개수 M */

/* committed 레코드 */
typedef struct { int bid, orient, px, py, entry, exit; } Rec;
static Rec **comm;       /* comm[bay] -> 배열 */
static int *comm_n, *comm_cap;
static double *bay_loads, *bay_weights;

/* ---- 마샬 읽기 ---- */
static uint8_t *BUF; static size_t POS, LEN;
static int ri32(void){ int v; memcpy(&v, BUF+POS, 4); POS+=4; return v; }
static int64_t ri64(void){ int64_t v; memcpy(&v, BUF+POS, 8); POS+=8; return v; }
static double rf64(void){ double v; memcpy(&v, BUF+POS, 8); POS+=8; return v; }
static uint64_t ru64(void){ uint64_t v; memcpy(&v, BUF+POS, 8); POS+=8; return v; }

static void load(const char *path){
    FILE *f=fopen(path,"rb"); if(!f){perror("in");exit(2);}
    fseek(f,0,SEEK_END); LEN=ftell(f); fseek(f,0,SEEK_SET);
    BUF=malloc(LEN); if(fread(BUF,1,LEN,f)!=LEN){perror("read");exit(2);} fclose(f);
    POS=0;
    if(ri32()!=MAGIC){fprintf(stderr,"bad magic\n");exit(2);}
    N_BAYS=ri32(); N_BLOCKS=ri32(); MAX_LAY=ri32(); WORDS=ri32();
    W1=rf64(); W2=rf64(); W3=rf64();
    bays=calloc(N_BAYS,sizeof(Bay));
    for(int j=0;j<N_BAYS;j++){ bays[j].W=ri32(); bays[j].H=ri32(); }
    blocks=calloc(N_BLOCKS,sizeof(Block));
    for(int i=0;i<N_BLOCKS;i++){
        Block *b=&blocks[i];
        b->release=ri32(); b->proc=ri32(); b->due=ri32(); b->workload=rf64();
        b->prefs=calloc(N_BAYS,sizeof(double));
        for(int j=0;j<N_BAYS;j++) b->prefs[j]=rf64();
        b->n_orient=ri32();
        b->or_=calloc(b->n_orient,sizeof(Orient));
        for(int o=0;o<b->n_orient;o++){
            Orient *O=&b->or_[o];
            O->r0=rf64(); O->r1=rf64(); O->r2=rf64(); O->r3=rf64();
            O->n_layers=ri32();
            O->lay=calloc(O->n_layers,sizeof(Layer));
            O->min_cx=O->min_cy=1<<29; O->max_cx=O->max_cy=-(1<<29);
            for(int k=0;k<O->n_layers;k++){
                Layer *L=&O->lay[k];
                L->my0=ri32(); L->mx0=ri32(); L->h=ri32();
                if(L->h>0){
                    L->rows=calloc((size_t)L->h*WORDS,sizeof(uint64_t));
                    for(int rr=0;rr<L->h*WORDS;rr++) L->rows[rr]=ru64();
                    /* 정수 셀 bbox: 각 행의 set 비트 범위 */
                    for(int ri=0;ri<L->h;ri++){
                        uint64_t *row=&L->rows[(size_t)ri*WORDS];
                        int found=0,lo=0,hi=0;  /* lo/hi=셀 좌표(음수 가능), found=셀 존재 */
                        for(int w=0;w<WORDS;w++){ if(row[w]){
                            for(int bit=0;bit<64;bit++) if(row[w]>>bit&1){
                                int cx=L->mx0 + w*64 + bit;
                                if(!found){lo=hi=cx;found=1;} else {if(cx<lo)lo=cx; if(cx>hi)hi=cx;} } } }
                        if(found){
                            int cyl=L->my0+ri;
                            if(lo<O->min_cx)O->min_cx=lo;
                            if(hi+1>O->max_cx)O->max_cx=hi+1; /* exclusive */
                            if(cyl<O->min_cy)O->min_cy=cyl;
                            if(cyl+1>O->max_cy)O->max_cy=cyl+1;
                        }
                    }
                }
            }
            if(O->max_cx<O->min_cx){O->min_cx=O->min_cy=0;O->max_cx=O->max_cy=0;}
        }
    }
    /* 배치 순서: M개(각 N_BLOCKS) */
    N_ORD=ri32();
    ORDERS=malloc((size_t)N_ORD*N_BLOCKS*sizeof(int));
    for(size_t i=0;i<(size_t)N_ORD*N_BLOCKS;i++) ORDERS[i]=ri32();
}

/* ---- 멀티워드 비트연산 ---- */
/* (src[WORDS] << s) 를 dst 에 OR */
static inline void shift_or(uint64_t *dst,const uint64_t *src,int s){
    int wsh=s>>6, bsh=s&63;
    for(int w=WORDS-1;w>=0;w--){
        int sidx=w-wsh; uint64_t v=0;
        if(sidx>=0){ v=src[sidx]<<bsh; if(bsh&&sidx-1>=0)v|=src[sidx-1]>>(64-bsh); }
        dst[w]|=v;
    }
}
/* (src[WORDS] << s) & occ[WORDS] 가 비-0인가 */
static inline int shift_and_nz(const uint64_t *src,const uint64_t *occ,int s){
    int wsh=s>>6, bsh=s&63;
    for(int w=WORDS-1;w>=0;w--){
        int sidx=w-wsh; uint64_t v=0;
        if(sidx>=0){ v=src[sidx]<<bsh; if(bsh&&sidx-1>=0)v|=src[sidx-1]>>(64-bsh); }
        if(v&occ[w]) return 1;
    }
    return 0;
}

/* occupancy 버퍼: layer*H*WORDS. 전역 재사용(최대 H로 alloc). */
static uint64_t *occE,*occX,*upE,*upX,*occNew;
static int MAXH;
static void alloc_occ(void){
    MAXH=0; for(int j=0;j<N_BAYS;j++) if(bays[j].H>MAXH)MAXH=bays[j].H;
    size_t sz=(size_t)MAX_LAY*MAXH*WORDS;
    occE=calloc(sz,sizeof(uint64_t)); occX=calloc(sz,sizeof(uint64_t));
    upE=calloc(sz,sizeof(uint64_t)); upX=calloc(sz,sizeof(uint64_t));
    occNew=calloc(sz,sizeof(uint64_t));
}
#define OCC(buf,k,y) (&(buf)[((size_t)(k)*MAXH+(y))*WORDS])

/* 한 블록을 occ 버퍼에 stamp(OR). H는 현 베이 높이. */
static void stamp(uint64_t *buf,int bid,int orient,int px,int py,int H){
    Orient *O=&blocks[bid].or_[orient];
    for(int k=0;k<O->n_layers && k<MAX_LAY;k++){
        Layer *L=&O->lay[k]; if(L->h==0)continue;
        for(int ri=0;ri<L->h;ri++){
            int wy=py+L->my0+ri; if(wy<0||wy>=H)continue;
            shift_or(OCC(buf,k,wy), &L->rows[(size_t)ri*WORDS], px+L->mx0);
        }
    }
}
/* crane_blocked: 블록(bid,orient)을 (px,py)에 놓을 때 up 버퍼와 충돌? */
static int crane_blocked(const uint64_t *up,int bid,int orient,int px,int py,int H){
    Orient *O=&blocks[bid].or_[orient];
    for(int k=0;k<O->n_layers && k<MAX_LAY;k++){
        Layer *L=&O->lay[k]; if(L->h==0)continue;
        for(int ri=0;ri<L->h;ri++){
            int wy=py+L->my0+ri; if(wy<0||wy>=H)continue;
            if(shift_and_nz(&L->rows[(size_t)ri*WORDS], OCC(up,k,wy), px+L->mx0)) return 1;
        }
    }
    return 0;
}
static void clear_occ(uint64_t *buf,int H){ memset(buf,0,(size_t)MAX_LAY*MAXH*WORDS*sizeof(uint64_t)); (void)H; }
static void build_upper(uint64_t *up,const uint64_t *occ,int H){
    for(int y=0;y<H;y++){
        for(int w=0;w<WORDS;w++){
            uint64_t acc=0;
            for(int k=MAX_LAY-1;k>=0;k--){ acc|=occ[((size_t)k*MAXH+y)*WORDS+w]; up[((size_t)k*MAXH+y)*WORDS+w]=acc; }
        }
    }
}

/* best_in_bay: (entry,px,py,orient,top_y) found? 반환 1/0, out_* 채움. */
static int best_in_bay(int bay,int bid,int r_time,int proc,
                       int *o_entry,int *o_px,int *o_py,int *o_orient,double *o_top){
    Bay *B=&bays[bay]; int H=B->H, Wd=B->W;
    Block *blk=&blocks[bid];
    /* candidate times: release + committed exits > release (정렬·유일) */
    int m=comm_n[bay];
    int *ct=malloc(sizeof(int)*(m+1)); int nct=0; ct[nct++]=r_time;
    for(int i=0;i<m;i++){ int e=comm[bay][i].exit; if(e>r_time) ct[nct++]=e; }
    /* 정렬+유일 */
    for(int a=0;a<nct;a++)for(int b=a+1;b<nct;b++) if(ct[b]<ct[a]){int t=ct[a];ct[a]=ct[b];ct[b]=t;}
    int u=0; for(int a=0;a<nct;a++){ if(a==0||ct[a]!=ct[a-1]) ct[u++]=ct[a]; } nct=u;

    int found=0;
    for(int ti=0; ti<nct && !found; ti++){
        int t=ct[ti], te=t+proc;
        clear_occ(occE,H); clear_occ(occX,H);
        /* present_entry / present_exit / reverse */
        int has_rev=0;
        static int *rev=NULL; static int rev_cap=0;
        if(rev_cap<m+1){ rev_cap=m+1; rev=realloc(rev,sizeof(int)*rev_cap); }
        int nrev=0;
        for(int i=0;i<m;i++){
            Rec *c=&comm[bay][i];
            int ov = (c->entry<te && t<c->exit);
            if(!ov) continue;
            if((c->entry<t && t<c->exit)||c->entry==t) stamp(occE,c->bid,c->orient,c->px,c->py,H);
            if((c->entry<te && te<c->exit)||c->exit==te) stamp(occX,c->bid,c->orient,c->px,c->py,H);
            if((t<c->entry&&c->entry<te)||c->entry==t||(t<c->exit&&c->exit<te)||c->exit==te){ rev[nrev++]=i; has_rev=1; }
        }
        build_upper(upE,occE,H); build_upper(upX,occX,H);

        double best_top=1e30; int bpx=0,bpy=0,bor=0, ok=0;
        for(int o=0;o<blk->n_orient;o++){
            Orient *O=&blk->or_[o];
            /* Python feasible_positions와 동일한 float 경계(ceil/floor) -- 후보집합 일치=품질 일치 */
            int px_lo=(int)ceil(-O->r0); if(px_lo<0)px_lo=0;
            int px_hi=(int)floor(Wd - O->r2);
            int py_lo=(int)ceil(-O->r1); if(py_lo<0)py_lo=0;
            int py_hi=(int)floor(H - O->r3);
            if(px_hi<px_lo||py_hi<py_lo) continue;
            /* 바닥 우선(py,px) 스캔, 첫 feasible(entry+exit+reverse) 채택(BLF) */
            int done=0;
            for(int py=py_lo; py<=py_hi && !done; py++){
                for(int px=px_lo; px<=px_hi; px++){
                    if(crane_blocked(upE,bid,o,px,py,H)) continue;   /* entry */
                    if(crane_blocked(upX,bid,o,px,py,H)) continue;   /* exit */
                    if(has_rev){
                        clear_occ(occNew,H); stamp(occNew,bid,o,px,py,H);
                        /* reverse: 각 rev 블록 c 가 새블록 crane(occNew의 upper)와 충돌? */
                        static uint64_t *upN=NULL; if(!upN) upN=calloc((size_t)MAX_LAY*MAXH*WORDS,sizeof(uint64_t));
                        build_upper(upN,occNew,H);
                        int blocked=0;
                        for(int rr=0;rr<nrev;rr++){ Rec *c=&comm[bay][rev[rr]];
                            if(crane_blocked(upN,c->bid,c->orient,c->px,c->py,H)){blocked=1;break;} }
                        if(blocked) continue;
                    }
                    double top_y = py + O->r3; /* Python: top_y = py + r3 */
                    if(top_y<best_top){ best_top=top_y; bpx=px;bpy=py;bor=o; ok=1; }
                    done=1; break; /* BLF: 이 방향 첫 자리 */
                }
            }
        }
        if(ok){ *o_entry=t;*o_px=bpx;*o_py=bpy;*o_orient=bor;*o_top=best_top; found=1; }
    }
    free(ct);
    return found;
}

/* empty-bay window entry (fallback): 가장 빠른 t>=release, [t,t+proc) 에 committed 없음 */
static int empty_bay_entry(int bay,int r_time,int proc){
    int entry=r_time, changed=1, m=comm_n[bay];
    while(changed){ changed=0;
        for(int i=0;i<m;i++){ Rec *c=&comm[bay][i];
            if(c->entry < entry+proc && entry < c->exit){ if(c->exit>entry){entry=c->exit;changed=1;} } }
    }
    return entry;
}

static void commit(int bay,int bid,int orient,int px,int py,int entry,int proc){
    if(comm_n[bay]>=comm_cap[bay]){ comm_cap[bay]=comm_cap[bay]?comm_cap[bay]*2:16;
        comm[bay]=realloc(comm[bay],sizeof(Rec)*comm_cap[bay]); }
    Rec *r=&comm[bay][comm_n[bay]++];
    r->bid=bid;r->orient=orient;r->px=px;r->py=py;r->entry=entry;r->exit=entry+proc;
    bay_loads[bay]+=blocks[bid].workload;
}

/* placement_cost obj2 근사 */
static double placement_cost(int bay,double tard,double workload,double pref_pen,double top_y){
    double new_load=bay_loads[bay]+workload, mx=0;
    for(int j=0;j<N_BAYS;j++) if(j!=bay){
        double d=bay_weights[bay]*new_load - bay_weights[j]*bay_loads[j]; if(d<0)d=-d;
        if(d>mx)mx=d; }
    return W1*tard + W2*mx + W3*pref_pen + 1e-4*top_y;
}

/* 출력 */
static int *out_buf; static int out_n;
static void place_block(int bid){
    Block *blk=&blocks[bid];
    int rt=blk->release, proc=blk->proc; double due=blk->due, wl=blk->workload;
    double s_max=0; for(int j=0;j<N_BAYS;j++) if(blk->prefs[j]>s_max)s_max=blk->prefs[j];
    int cbay=-1,cpx=0,cpy=0,cor=0,centry=0; double cbest=0;
    for(int bay=0;bay<N_BAYS;bay++){
        int entry,px,py,orient; double top;
        if(!best_in_bay(bay,bid,rt,proc,&entry,&px,&py,&orient,&top)) continue;
        double tard = (entry+proc-due)>0 ? (entry+proc-due):0;
        double pref_pen = s_max - blk->prefs[bay];
        double cost = placement_cost(bay,tard,wl,pref_pen,top);
        if(cbay<0||cost<cbest){ cbest=cost;cbay=bay;cpx=px;cpy=py;cor=orient;centry=entry; }
    }
    if(cbay<0){ /* fallback: 빈-베이 윈도우 */
        int best_bay=-1,best_entry=1<<30,best_or=0,best_px=0,best_py=0;
        for(int bay=0;bay<N_BAYS;bay++){ Bay *B=&bays[bay];
            for(int o=0;o<blk->n_orient;o++){ Orient *O=&blk->or_[o];
                int px=(int)ceil(-O->r0); if(px<0)px=0;
                int py=(int)ceil(-O->r1); if(py<0)py=0;
                if(O->r2+px>B->W || O->r3+py>B->H) continue; /* 안 맞음(float 경계) */
                int e=empty_bay_entry(bay,rt,proc);
                if(e<best_entry){best_entry=e;best_bay=bay;best_or=o;best_px=px;best_py=py;} break; } }
        if(best_bay<0){ best_bay=0; best_or=0; best_px=0; best_py=0; best_entry=empty_bay_entry(0,rt,proc); }
        cbay=best_bay;cor=best_or;cpx=best_px;cpy=best_py;centry=best_entry;
    }
    commit(cbay,bid,cor,cpx,cpy,centry,proc);
    int *o=&out_buf[out_n*7]; out_n++;
    o[0]=bid;o[1]=cbay;o[2]=cpx;o[3]=cpy;o[4]=cor;o[5]=centry;o[6]=centry+proc;
}

/* 현 committed 상태에서 총 obj(검증기 objective 공식과 동일) -- 배치 내 랭킹용 */
static double compute_obj(void){
    double obj1=0;
    for(int b=0;b<N_BAYS;b++) for(int k=0;k<comm_n[b];k++){
        Rec *r=&comm[b][k]; int due=blocks[r->bid].due;
        if(r->exit>due) obj1 += (double)(r->exit-due);
    }
    double obj2=0;
    if(N_BAYS>=2) for(int i=0;i<N_BAYS;i++) for(int j=0;j<N_BAYS;j++) if(i!=j){
        double dd=bay_weights[i]*bay_loads[i]-bay_weights[j]*bay_loads[j]; if(dd<0)dd=-dd;
        if(dd>obj2)obj2=dd; }
    obj2=floor(obj2);
    double obj3=0;
    for(int b=0;b<N_BAYS;b++) for(int k=0;k<comm_n[b];k++){
        Rec *r=&comm[b][k]; double *p=blocks[r->bid].prefs, mx=0;
        for(int j=0;j<N_BAYS;j++) if(p[j]>mx)mx=p[j];
        obj3 += mx - p[b];   /* 배정 베이 = b */
    }
    return W1*obj1 + W2*obj2 + W3*obj3;
}

int main(int argc,char**argv){
    if(argc<3){fprintf(stderr,"usage: scan in out\n");return 2;}
    load(argv[1]);
    comm=calloc(N_BAYS,sizeof(Rec*)); comm_n=calloc(N_BAYS,sizeof(int));
    comm_cap=calloc(N_BAYS,sizeof(int));
    bay_loads=calloc(N_BAYS,sizeof(double)); bay_weights=calloc(N_BAYS,sizeof(double));
    double tot=0; for(int j=0;j<N_BAYS;j++) tot+=(double)bays[j].W*bays[j].H;
    double avg=tot/N_BAYS;
    for(int j=0;j<N_BAYS;j++) bay_weights[j]=avg/((double)bays[j].W*bays[j].H);
    alloc_occ();
    out_buf=malloc(sizeof(int)*7*N_BLOCKS);
    int *best_buf=malloc(sizeof(int)*7*N_BLOCKS); int best_n=0; double best_obj=-1;
    double max_s = (argc>3) ? atof(argv[3]) : 0.0;   /* 0=무제한, >0=벽시계 상한(초) */
    struct timespec t0; clock_gettime(CLOCK_MONOTONIC,&t0);
    double last_dur = 0.0;   /* 직전 순서 construct 소요(다음 순서 예측용) */
    /* 배치: M개 순서를 각각 construct, 내부 obj로 best 선택. *정밀* 시간 가드 -- 매 순서마다
     * 체크하고, "현 경과 + 직전 순서 소요"가 max_s를 넘으면 다음 순서를 *시작하지 않는다*
     * (overshoot 0 보장). 대형은 순서당 수 초라 옛 8순서마다 체크는 max_s를 크게 넘겼다.
     * m=0(EDD)은 항상 돌아 ≥1 결과를 보장한다(최악=단일 EDD=옛 동작, 무회귀). */
    for(int m=0;m<N_ORD;m++){
        if(max_s>0 && m>0){
            struct timespec tn; clock_gettime(CLOCK_MONOTONIC,&tn);
            double el=(tn.tv_sec-t0.tv_sec)+(tn.tv_nsec-t0.tv_nsec)/1e9;
            if(el + last_dur > max_s) break;   /* 다음 순서가 예산 내 못 끝남 -> 정지 */
        }
        struct timespec ts; clock_gettime(CLOCK_MONOTONIC,&ts);
        for(int b=0;b<N_BAYS;b++){ comm_n[b]=0; bay_loads[b]=0; }
        out_n=0;
        int *ord=&ORDERS[(size_t)m*N_BLOCKS];
        for(int s=0;s<N_BLOCKS;s++) place_block(ord[s]);
        double obj=compute_obj();
        if(best_obj<0 || obj<best_obj){
            best_obj=obj; best_n=out_n;
            memcpy(best_buf,out_buf,sizeof(int)*7*(size_t)out_n);
        }
        struct timespec te; clock_gettime(CLOCK_MONOTONIC,&te);
        last_dur=(te.tv_sec-ts.tv_sec)+(te.tv_nsec-ts.tv_nsec)/1e9;
    }
    FILE *f=fopen(argv[2],"wb"); if(!f){perror("out");return 2;}
    fwrite(&best_obj,8,1,f); fwrite(&best_n,4,1,f); fwrite(best_buf,4,7*best_n,f);
    fclose(f);
    return 0;
}
