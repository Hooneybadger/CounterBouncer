import ctypes

def algorithm(prob_info, timelimit = 60):

    # --- 1. Load the compiled C++ shared library ---

    lib_name = f"lib_myalgorithm.so"
    
    cpp_lib = ctypes.CDLL(f'./{lib_name}')

    # --- 2. Define the function signatures (argument and return types) ---

    # void solve(...)
    cpp_lib.solve.argtypes = [
        # === INPUTS ===
        ctypes.c_int,                       # num_nodes
        ctypes.c_int,                       # num_ports
        ctypes.c_int,                       # fixed_cost
        ctypes.c_int,                       # num_edges
        ctypes.POINTER(ctypes.c_int),       # edges
        ctypes.c_int,                       # num_demands
        ctypes.POINTER(ctypes.c_int),       # od_pairs
        ctypes.POINTER(ctypes.c_int),       # demands
        ctypes.c_int,                       # time_limit

        # === OUTPUTS (passed by reference) ===
        ctypes.POINTER(ctypes.c_int),       # out_port_route_num
        ctypes.POINTER(ctypes.c_int),       # out_demand_indices
        ctypes.POINTER(ctypes.c_int),       # out_route_lengths
        ctypes.POINTER(ctypes.c_int),       # out_routes
    ]
    cpp_lib.solve.restype = None

    # Note: The free_solution_memory function is removed as it's incompatible 
    # with memory allocated by Python's ctypes. Python's garbage collector
    # will manage the memory for the output arrays.

    # --- 3. Extract data from prob_info and convert to C types ---

    num_nodes = prob_info['N']
    num_ports = prob_info['P']
    fixed_cost = prob_info['F']
    edges_flat = [node for pair in prob_info['E'] for node in pair]
    num_edges = len(prob_info['E'])
    c_edges = (ctypes.c_int * len(edges_flat))(*edges_flat)
    od_pairs = [item[0] for item in prob_info['K']]
    demands = [item[1] for item in prob_info['K']]
    num_demands = len(demands)
    od_pairs_flat = [port for pair in od_pairs for port in pair]
    c_od_pairs = (ctypes.c_int * len(od_pairs_flat))(*od_pairs_flat)
    c_demands = (ctypes.c_int * len(demands))(*demands)

    # --- 4. Prepare output arrays for C++ to fill ---
    # Since the C++ function expects pre-allocated buffers, we must create them here.
    # We'll estimate a safe upper bound for the size of the route-related arrays.
    
    c_out_port_route_num = (ctypes.c_int * num_ports)()

    # Set the maximum number of routes
    max_num_routes = sum(2 * (od_pairs[i][1] - od_pairs[i][0]) * demands[i] for i in range(len(od_pairs)))

    # Set the maximum total route length
    max_total_route_len = max_num_routes * num_nodes
    
    c_out_demand_indices = (ctypes.c_int * max_num_routes)()
    c_out_route_lengths = (ctypes.c_int * max_num_routes)()
    c_out_routes = (ctypes.c_int * max_total_route_len)()

    # --- 5. Call the C++ function ---
    cpp_lib.solve(
        num_nodes,
        num_ports,
        fixed_cost,
        num_edges,
        c_edges,
        num_demands,
        c_od_pairs,
        c_demands,
        timelimit,
        c_out_port_route_num,
        c_out_demand_indices,
        c_out_route_lengths,
        c_out_routes
    )

    # --- 6. Parse the results from C arrays back to Python objects ---

    # Initialize the solution as a dictionary with a list for each port
    solution = {p: [] for p in range(num_ports)}

    # A cursor for the flattened route data (demand indices and lengths)
    route_data_cursor = 0
    # A cursor for the concatenated path nodes in c_out_routes
    path_nodes_cursor = 0

    # Iterate through each port to find its routes
    for port_idx in range(num_ports):
        # Get the number of routes assigned to this specific port
        num_routes_for_port = c_out_port_route_num[port_idx]

        # Process each route for the current port
        for _ in range(num_routes_for_port):
            # Get the length and demand index for the current route
            route_len = c_out_route_lengths[route_data_cursor]
            demand_k = c_out_demand_indices[route_data_cursor]
            
            # Slice the flat C array to get the nodes for the current route
            route_end = path_nodes_cursor + route_len
            route = [c_out_routes[j] for j in range(path_nodes_cursor, route_end)]
            
            # Append the result to the correct port's list in the solution dictionary
            # The format is a list containing the route (list) and demand index (int)
            solution[port_idx].append([route, demand_k])
            
            # Move the cursors to the start of the next route's data
            path_nodes_cursor += route_len
            route_data_cursor += 1

    return solution