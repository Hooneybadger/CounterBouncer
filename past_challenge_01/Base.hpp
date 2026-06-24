#pragma once

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
#include <unordered_map>

#include "gurobi_c++.h"

#include "./json.hpp"
using json = nlohmann::json;



using namespace std;
namespace fs = std::filesystem;

using PortId = int;
using NodeId = int;
using Distance = int;
using Demand = int;
using Cost = int;

const int INF = ~0u >> 1; // Sufficiently Big number
const double TOL = 1e-3;

inline const int idx2(const int i, const int j, const int n) { return i * n + j; }
inline const int idx3(const int i, const int j, const int k, const int n, const int m) { return i * n * m + j * m + k; }
