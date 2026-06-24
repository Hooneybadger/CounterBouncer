#include "./Base.hpp"
#include "./Graph.hpp"
#include "./function.hpp"

// The extern "C" block prevents C++ name mangling,
// ensuring that Python's ctypes can find the functions by their C-style names.
extern "C"
{
    /**
     * @brief The main algorithm function to be called from Python.
     *
     * === INPUTS ===
     * @param num_nodes Total number of nodes in the graph.
     * @param num_ports Total number of ports.
     * @param fixed_cost The fixed cost per vehicle trip (fCost).
     * @param num_edges Total number of edges in the graph.
     * @param edges A flattened 1D array of edges, e.g., [u1, v1, u2, v2, ...]. Size is num_edges * 2.
     * @param num_demands Total number of OD pairs (demands).
     * @param od_pairs A flattened 1D array of origin-destination pairs, e.g., [o1, d1, o2, d2, ...]. Size is num_demands * 2.
     * @param demands An array of demand quantities corresponding to each OD pair. Size is num_demands.
     * @param time_limit The time limit for the algorithm in seconds.
     *
     * === OUTPUTS ===
     * @param out_port_route_num Stores the number of routes for each port.
     * @param out_demand_indices Stores the demand index 'k' for each route.
     * @param out_route_lengths Stores the length of each route.
     * @param out_routes Concatenation of all routes
     */
    void solve(
        // === INPUTS ===
        int num_nodes,
        int num_ports,
        int fixed_cost,
        int num_edges,
        const int* edges,
        int num_demands,
        const int* od_pairs,
        const int* demands,
        int time_limit,

        // === OUTPUTS (passed by reference) ===
        int* out_port_route_num,
        int* out_demand_indices,
        int* out_route_lengths,
        int* out_routes
    )
{
    // Store current time
    auto start_time = chrono::steady_clock::now();

    // Parameter setting for experiment
    // ofstream log_file("log.txt");

    const double postprocessingTime = 2.0; // seconds
    const double Heur_proportion = 0.15;
    const double noRelThreshold = 10000; // if problem size (num_nodes * num_ports * (num_ports-1) / 2) < noRelThreshold, do not use noRelHeuristic. Else, only use noRelHeuristic.

    // Initialize Gurobi environment and model
    GRBEnv env = GRBEnv(true);
    env.start();
    GRBModel model(env);
    // Set Gurobi model parameters

    model.set(GRB_IntParam_OutputFlag, 0); // Suppress output

    model.set(GRB_DoubleParam_MIPGapAbs, 2 - TOL); // Set absolute MIP gap to 2, which is valid unless there is no odd circuit in the deck graph
    // model.set(GRB_IntParam_Cuts, 0); // Disable all cuts

    const int solutionPoolSize = 1;
    model.set(GRB_IntParam_PoolSolutions, solutionPoolSize);

    model.set(GRB_IntParam_Method, 2); // Use barrier method to solve root LP relaxation
    model.set(GRB_IntParam_Crossover, 0); // Disable crossover

    // -----------------------------------------------------------------
    // Reconstruct data structures (e.g., graph, demand list)
    // from the input C-style arrays.
    // -----------------------------------------------------------------

    vector<Node> nodeVec(num_nodes);

    for (int i = 0; i < num_edges; ++i)
    {
        const NodeId v1 = edges[i * 2];
        const NodeId v2 = edges[i * 2 + 1];
        nodeVec[v1]._neighborVec.push_back(v2);
        nodeVec[v2]._neighborVec.push_back(v1);
    }
    
    vector<NodeId> demand_origin(num_demands);
    vector<NodeId> demand_dest(num_demands);
    vector<int> demand_quantity(num_demands);
    for (int i = 0; i < num_demands; ++i)
    {
        demand_origin[i] = od_pairs[i * 2];
        demand_dest[i] = od_pairs[i * 2 + 1];
        demand_quantity[i] = demands[i];
    }

    vector<int> demandQuantityVec(num_ports * num_ports, 0); // demand quantity for all o-d pairs
    for (int demand = 0; demand < num_demands; ++demand)
    {
        const PortId p = demand_origin[demand];
        const PortId q = demand_dest[demand];
        demandQuantityVec[idx2(p, q, num_ports)] = demand_quantity[demand];
    }

    // -----------------------------------------------------------------
    // Set arc orientation
    vector<NodeId> positionVec;
    getBFSOrientation(nodeVec, positionVec);

    // Create decision variables
    vector<GRBVar> x_pqi(num_ports * num_ports * num_nodes); // 1 if a car is loaded at port p and unloaded at port q at node i
    vector<GRBVar> y_pi(num_ports * num_nodes); // 1 if node i is accessible from root at port p
    vector<GRBVar> z_pqr(num_ports * num_ports * num_ports); // amount of demand split of (p->r) to (p->q and q->r)

    // Formulate
    formulate(nodeVec, num_ports, num_nodes, demandQuantityVec, fixed_cost,
                model, x_pqi, y_pi, z_pqr);

    const double IPComputationTime = time_limit - chrono::duration_cast<chrono::seconds>(chrono::steady_clock::now() - start_time).count() - postprocessingTime;
    model.set(GRB_DoubleParam_TimeLimit, IPComputationTime); // Set time limit
    model.set(GRB_DoubleParam_Heuristics, Heur_proportion); // Set proportion of solver heuristics (default: 0.05)

    // Determines to use Gurobi noRelHeur, based on problem size
    const int problemSize = num_nodes * num_ports * (num_ports-1) / 2; // The number of x_pqi variables
    if (problemSize > noRelThreshold) model.set(GRB_DoubleParam_NoRelHeurTime, IPComputationTime); // Use noRelHeur
    
    // Solve the model
    model.optimize();
    
    // Postprocess 
    
    // vectors corresponding to arrays to return
    vector<int> outPortRouteVec(num_ports, 0);
    vector<int> outDemandIndicesVec;
    vector<int> outRouteLengthsVec;
    vector<int> outRoutesVec;

    // Get solution
    get_solution(nodeVec, num_ports, num_nodes, num_demands,
        demand_origin, demand_dest, demand_quantity, fixed_cost,
        model, x_pqi, y_pi, z_pqr,
        outPortRouteVec, outDemandIndicesVec, outRouteLengthsVec, outRoutesVec);

    // Make output to return: 
    std::copy(outPortRouteVec.begin(), outPortRouteVec.end(), out_port_route_num);
    std::copy(outDemandIndicesVec.begin(), outDemandIndicesVec.end(), out_demand_indices);
    std::copy(outRouteLengthsVec.begin(), outRouteLengthsVec.end(), out_route_lengths);
    std::copy(outRoutesVec.begin(), outRoutesVec.end(), out_routes);
}
}