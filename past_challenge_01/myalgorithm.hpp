#pragma once

extern "C"
{

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

    // === USER PARAMETERS ===
    // ofstream& log_file,

    // === OUTPUTS (passed by reference) ===
    int* out_port_routes,
    int* out_demand_indices,
    int* out_route_lengths,
    int* out_routes
);

}