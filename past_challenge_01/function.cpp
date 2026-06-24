#include "./function.hpp"

/* 
    Get BFS orientation of the graph, based on node accessibility status.
    It performs BFS and sets each node's predecessor, minimum distance from the root node, and position.
*/
void getBFSOrientation(vector<Node>& nodeVec, vector<NodeId>& positionVec)
{
    positionVec.clear();

    for (Node& node : nodeVec)
    {
        node._pred = INF; // Reset predecessor to a large value, indicating that the predecessor has not been set yet
        node._position = INF; // Reset position to a large value
        node._dist = INF; // Reset distance to a large value
    }

    vector<NodeId> search(1, 0); // Start from the root node
    NodeId position = 0;
    nodeVec[0]._dist = 0; // Distance from root is 0
    nodeVec[0]._pred = -1;
    while (!search.empty())
    {
        vector<NodeId> nextSearch;
        for (NodeId id : search)
        {
            positionVec.push_back(id);
            nodeVec[id]._position = position++;
            for (NodeId nbr : nodeVec[id]._neighborVec)
            {
                if (nodeVec[nbr]._accessible && nodeVec[nbr]._pred == INF)
                {
                    nodeVec[nbr]._pred = id; // Set predecessor
                    nodeVec[nbr]._dist = nodeVec[id]._dist + 1; // Update distance
                    nextSearch.push_back(nbr);
                }
            }
        }
        search.swap(nextSearch);
    }
}

void formulate(vector<Node>& nodeVec, int num_ports, int num_nodes, vector<int>& demandQuantityVec, int fixed_cost,
                 GRBModel& model, vector<GRBVar>& x_pqi, vector<GRBVar>& y_pi, vector<GRBVar>& z_pqr)
{
    // Add decision variables x_pqi to the model
    for (PortId p = 0; p < num_ports - 1; ++p)
    {
        for (PortId q = p + 1; q < num_ports; ++q)
        {
            for (NodeId i = 1; i < num_nodes; ++i) // Exclude the root node (0)
            {
                x_pqi[idx3(p, q, i, num_ports, num_nodes)] = model.addVar(0.0, 1.0, 0.0, GRB_BINARY, "x_" + to_string(p) + "_" + to_string(q) + "_" + to_string(i));
            }
        }
    }

    // Add decision variables y_pi to the model
    for (PortId p = 1; p < num_ports - 1; ++p)
    {
        for (NodeId i = 0; i < num_nodes; ++i)
        {
            y_pi[idx2(p, i, num_nodes)] = model.addVar(0.0, 1.0, 0.0, GRB_BINARY, "y_" + to_string(p) + "_" + to_string(i));
        }
        model.addConstr(y_pi[idx2(p, 0, num_nodes)] == 1.0); // The root node is always accessible
    }

    // Add decision variables z_pqr to the model
    for (PortId p = 0; p < num_ports - 2; ++p)
    {
        for (PortId q = p + 1; q < num_ports - 1; ++q)
        {
            for (PortId r = q + 1; r < num_ports; ++r)
            {
                z_pqr[idx3(p, q, r, num_ports, num_ports)] = model.addVar(0.0, GRB_INFINITY, 0.0, GRB_INTEGER, "z_" + to_string(p) + "_" + to_string(q) + "_" + to_string(r));
            }
        }
    }
    
    for (PortId p = 0; p < num_ports - 1; ++p)
    {
        for (PortId q = p+1; q < num_ports; ++q)
        {
            GRBLinExpr lhs = 0.0;
            for (NodeId i = 1; i < num_nodes; ++i)
            {
                lhs += x_pqi[idx3(p, q, i, num_ports, num_nodes)];
            }
            for (PortId r = p+1; r < q; ++r) lhs += z_pqr[idx3(p, r, q, num_ports, num_ports)];
            for (PortId r = 0; r < p; ++r) lhs -= z_pqr[idx3(r, p, q, num_ports, num_ports)];
            for (PortId r = q+1; r < num_ports; ++r) lhs -= z_pqr[idx3(p, q, r, num_ports, num_ports)];
            model.addConstr(lhs == demandQuantityVec[idx2(p, q, num_ports)], "Demand_" + to_string(p) + "_" + to_string(q));
        }
    }

    // Adding constraints - accessibility propagation
    for (NodeId i = 1; i < num_nodes; ++i)
    {
        vector<NodeId> predVec;
        for (NodeId neighbor : nodeVec[i]._neighborVec)
        {
            if (nodeVec[neighbor]._position < nodeVec[i]._position)
            {
                predVec.push_back(neighbor);
            }
        }
        for (PortId p = 1; p < num_ports - 1; ++p)
        {
            GRBLinExpr expr = 0.0;
            for (NodeId j : predVec)
            {
                expr += y_pi[idx2(p, j, num_nodes)];
            }
            model.addConstr(expr >= y_pi[idx2(p, i, num_nodes)]);
        }
    }

    // Adding constraints - ensuring acceessibility of unloading nodes
    for (PortId q = 1; q < num_ports - 1; ++q)
    {
        for (NodeId i = 1; i < num_nodes; ++i)
        {
            GRBLinExpr expr = 0.0;
            for (PortId p = 0; p < q; ++p)
            {
                expr += x_pqi[idx3(p, q, i, num_ports, num_nodes)];
            }
            model.addConstr(expr <= y_pi[idx2(q, i, num_nodes)], "Unloading_Accessibility_" + to_string(q) + "_" + to_string(i));
        }
    }

    // Adding constraints - ensuring acceessibility of loading nodes
    for (PortId p = 1; p < num_ports - 1; ++p)
    {
        for (NodeId i = 1; i < num_nodes; ++i)
        {
            GRBLinExpr expr = 0.0;
            for (PortId q = p + 1; q < num_ports; ++q)
            {
                expr += x_pqi[idx3(p, q, i, num_ports, num_nodes)];
            }
            model.addConstr(expr <= y_pi[idx2(p, i, num_nodes)], "Loading_Accessibility_" + to_string(p) + "_" + to_string(i));
        }
    }

    // Adding constraints - forcing inaccessibility of occupied nodes
    for (PortId q = 1; q < num_ports - 1; ++q)
    {
        for (NodeId i = 1; i < num_nodes; ++i)
        {
            GRBLinExpr expr = 0.0;
            for (PortId p = 0; p < q; ++p)
            {
                for (PortId r = q + 1; r < num_ports; ++r)
                {
                    expr += x_pqi[idx3(p, r, i, num_ports, num_nodes)];
                }
            }
            model.addConstr(expr <= 1 - y_pi[idx2(q, i, num_nodes)], "Occupied_Node_Inaccessibility_" + to_string(q) + "_" + to_string(i));
        }
    }

    // Set the objective function
    GRBLinExpr objective = 0.0;
    for (PortId p = 0; p < num_ports - 1; ++p)
    {
        for (PortId q = p + 1; q < num_ports; ++q)
        {
            for (NodeId i = 1; i < num_nodes; ++i)
            {
                objective += x_pqi[idx3(p, q, i, num_ports, num_nodes)] * (2 * (nodeVec[i]._dist + fixed_cost));
            }
        }
    }

    model.setObjective(objective, GRB_MINIMIZE);
}

void get_solution(vector<Node>& nodeVec, int num_ports, int num_nodes, int num_demands,
    vector<PortId>& demand_origin, vector<PortId>& demand_dest, vector<int>& demand_quantity, int fixed_cost,
    GRBModel& model, vector<GRBVar>& x_pqi, vector<GRBVar>& y_pi, vector<GRBVar>& z_pqr,
    vector<int>& portRouteNumVec, vector<int>& routeDemandIndexVec, vector<int>& routeLengthVec, vector<int>& routeVec)
{
    portRouteNumVec.resize(num_ports);
    fill(portRouteNumVec.begin(), portRouteNumVec.end(), 0);

    vector<int> occupyingDemandIdVec(num_nodes);
    vector<vector<int>> demandIdVec = getDemandIdVec(num_ports, num_demands, demand_origin, demand_dest, demand_quantity, z_pqr);

    for (PortId currentPortId = 0; currentPortId < num_ports; ++currentPortId) // Iterate through each port to construct solution
    {
        // Get node accessibility information from the IP solution
        getAccessibilityInfo(nodeVec, currentPortId, num_nodes, num_ports, x_pqi);

        // Perform BFS search
        vector<NodeId> positionVec;
        getBFSOrientation(nodeVec, positionVec);

        // Unloading
        if (currentPortId > 0) // Exclude the first port
        {
            for (int position = 1; position < positionVec.size(); ++position) // Unload from smallest to largest position
            {
                const NodeId currentNodeId = positionVec[position];
                for (PortId p = 0; p < currentPortId; ++p)
                {
                    if (x_pqi[idx3(p, currentPortId, currentNodeId, num_ports, num_nodes)].get(GRB_DoubleAttr_X) > 1 - TOL)
                    {
                        // Unload car and store the corresponding information
                        ++portRouteNumVec[currentPortId];
                        routeDemandIndexVec.push_back(occupyingDemandIdVec[currentNodeId]);
                        vector<NodeId> unloadingRoute = getUnloadingRoute(nodeVec, currentNodeId);
                        routeLengthVec.push_back(unloadingRoute.size());
                        routeVec.insert(routeVec.end(), unloadingRoute.begin(), unloadingRoute.end());
                    }
                }
            }
        }

        // Loading
        if (currentPortId < num_ports - 1) // Exclude the last port
        {
            for (int position = positionVec.size() - 1; position > 0; --position) // Load to largest to smallest position
            {
                const NodeId currentNodeId = positionVec[position];
                for (PortId r = currentPortId + 1; r < num_ports; ++r)
                {
                    if (x_pqi[idx3(currentPortId, r, currentNodeId, num_ports, num_nodes)].get(GRB_DoubleAttr_Xn) > 1 - TOL)
                    {
                        // Load car and store the corresponding information
                        ++portRouteNumVec[currentPortId];
                        const int demandId = demandIdVec[idx2(currentPortId, r, num_ports)].back();
                        demandIdVec[idx2(currentPortId, r, num_ports)].pop_back();
                        routeDemandIndexVec.push_back(demandId);
                        vector<NodeId> unloadingRoute = getUnloadingRoute(nodeVec, currentNodeId);
                        routeLengthVec.push_back(unloadingRoute.size());
                        routeVec.insert(routeVec.end(), unloadingRoute.rbegin(), unloadingRoute.rend());
                    }
                }
            }
        }
    }
}

void getAccessibilityInfo(vector<Node>& nodeVec, PortId currentPortId, int num_nodes, int num_ports, vector<GRBVar>& x_pqi)
{
    // At the first and the last port, all nodes are accessible
    if (currentPortId == 0 || currentPortId == num_ports - 1)
    {
        for (NodeId i = 0; i < num_nodes; ++i) nodeVec[i]._accessible = true;
        return;
    }

    // At the middle ports, check inaccessibility based on the IP solution
    for (NodeId i = 1; i < num_nodes; ++i)
    {
        bool inaccessibility_found = false;
        for (PortId p = 0; p < currentPortId; ++p)
        {
            for (PortId r = currentPortId + 1; r < num_ports; ++r)
            {
                if (x_pqi[idx3(p, r, i, num_ports, num_nodes)].get(GRB_DoubleAttr_X) > 1 - TOL)
                {
                    inaccessibility_found = true;
                    break;
                }
            }
            if (inaccessibility_found) break;
        }
        nodeVec[i]._accessible = ! inaccessibility_found;
    }
}

vector<vector<int>> getDemandIdVec(int num_ports, int num_demands, vector<PortId>& demand_origin, vector<PortId>& demand_dest, vector<int>& demand_quantity, vector<GRBVar>& z_pqr)
{
    vector<vector<int>> demandIdVec(num_ports * num_ports); // To obtain demand index for (origin, destination) pairs

    for (int demand_id = 0; demand_id < num_demands; ++demand_id)
    {
        const PortId origin = demand_origin[demand_id];
        const PortId destination = demand_dest[demand_id];
        demandIdVec[idx2(origin, destination, num_ports)].resize(demand_quantity[demand_id]);
        std::fill(demandIdVec[idx2(origin, destination, num_ports)].begin(), demandIdVec[idx2(origin, destination, num_ports)].end(), demand_id);
    }

    unordered_map<tuple<PortId, PortId, PortId>, int> remainingSplitAmountMap; // Remaining split amount for each (p, q, r) triplet

    for (PortId p = 0; p < num_ports - 2; ++p)
    {
        for (PortId q = p + 1; q < num_ports - 1; ++q)
        {
            for (PortId r = q + 1; r < num_ports; ++r)
            {
                const int splitAmount = std::round(z_pqr[idx3(p, q, r, num_ports, num_ports)].get(GRB_DoubleAttr_X));
                if (splitAmount > 0)
                {
                    remainingSplitAmountMap[make_tuple(p, q, r)] = splitAmount; // Store the remaining split amount
                }
            }
        }
    }

    int num_leftSplit = remainingSplitAmountMap.size();
    while (num_leftSplit > 0)
    {
        for (auto [key, value] : remainingSplitAmountMap)
        {
            const PortId p = get<0>(key);
            const PortId q = get<1>(key);
            const PortId r = get<2>(key);

            int splitAmount = std::min(value, static_cast<int>(demandIdVec[idx2(p, r, num_ports)].size()));
            if (splitAmount == 0) continue; // Skip if no split amount is available

            for (int j = 0; j < splitAmount; ++j)
            {
                const int demandId = demandIdVec[idx2(p, r, num_ports)].back();
                demandIdVec[idx2(p, r, num_ports)].pop_back();
                demandIdVec[idx2(p, q, num_ports)].push_back(demandId);
                demandIdVec[idx2(q, r, num_ports)].push_back(demandId);
            }
            remainingSplitAmountMap[key] -= splitAmount; // Update the remaining split amount
            if (splitAmount == value)
            {
                --num_leftSplit;
            }
        }
    }

    return demandIdVec;
}

vector<NodeId> getUnloadingRoute(vector<Node>& nodeVec, NodeId currentNodeId)
{
    vector<NodeId> unloadingRoute;

    NodeId currentId = currentNodeId;
    // Traverse the parent nodes to find the unloading route
    while (currentId != 0) // Until we reach the root
    {
        unloadingRoute.push_back(currentId);
        currentId = nodeVec[currentId]._pred;
    }
    unloadingRoute.push_back(0); // Add the root node (0) at the end

    return unloadingRoute;
}