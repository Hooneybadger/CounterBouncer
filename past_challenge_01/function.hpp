#pragma once
#include "./Base.hpp"
#include "./Graph.hpp"

namespace std {
    template <>
    struct hash<std::tuple<PortId, PortId, PortId>> {
        size_t operator()(const std::tuple<PortId, PortId, PortId>& t) const {
            auto hash1 = std::hash<PortId>{}(std::get<0>(t));
            auto hash2 = std::hash<PortId>{}(std::get<1>(t));
            auto hash3 = std::hash<PortId>{}(std::get<2>(t));

            // A common way to combine hash values
            size_t seed = hash1;
            seed ^= hash2 + 0x9e3779b9 + (seed << 6) + (seed >> 2);
            seed ^= hash3 + 0x9e3779b9 + (seed << 6) + (seed >> 2);
            return seed;
        }
    };
}

void getBFSOrientation(vector<Node>& nodeVec, vector<NodeId>& positionVec);
void formulate(vector<Node>& nodeVec, int num_ports, int num_nodes, vector<int>& demandQuantityVec, int fixed_cost,
                 GRBModel& model, vector<GRBVar>& x_pqi, vector<GRBVar>& y_pi, vector<GRBVar>& z_pqr);
void get_solution(vector<Node>& nodeVec, int num_ports, int num_nodes, int num_demands,
    vector<PortId>& demand_origin, vector<PortId>& demand_dest, vector<int>& demand_quantity, int fixed_cost,
    GRBModel& model, vector<GRBVar>& x_pqi, vector<GRBVar>& y_pi, vector<GRBVar>& z_pqr,
    vector<int>& outPortRouteVec, vector<int>& outDemandIndicesVec, vector<int>& outRouteLengthsVec, vector<int>& outRoutesVec);
void getAccessibilityInfo(vector<Node>& nodeVec, PortId currentPortId, int num_nodes, int num_ports, vector<GRBVar>& x_pqi);
vector<vector<int>> getDemandIdVec(int num_ports, int num_demands, vector<PortId>& demand_origin, vector<PortId>& demand_dest, vector<int>& demand_quantity, vector<GRBVar>& z_pqr);
vector<NodeId> getUnloadingRoute(vector<Node>& nodeVec, NodeId currentNodeId);