//
// Created by swee on 3/21/18.
//

#include "Node.h"
#include <cmath>

Node::Node() {

}

Node::Node(Node* _parent,int index,double xl,double yl,double zl,double psil,double vsl,double speedl){
    parent = _parent;
    x = xl;
    y = yl;
    z = zl;
    vx = 0;
    vy = 0;
    vz = 0;
    psi = psil;
    vs = vsl;
    speed = speedl;
    g = 0;
    h = 0;
    neighborhood = 5;
}

double Node::NodeDist(Node B) {
    return sqrt(pow((x - B.x),2) + pow((y - B.y),2) );
}

bool Node::GoalCheck(Node goal) {
    if (NodeDist(goal) < neighborhood)
        return true;
    else
        return false;
}

bool Node::AddChild(Node child) {
    std::list<Node>::iterator it;
    for(it=children.begin();it!=children.end();++it){
        if(it->index == child.index)
            return false;
    }
    children.push_back(child);
}


void Node::GenerateChildren(int lenH,int lenV,double* heading, double* vspeed, double dt, std::list<Node> *nodeList) {
    for(int i=0;i<lenH;++i){
        for(int j=0;j<lenV;++j){
            double xnew,ynew,znew;
            double dpsi = heading[i];
            double dvs = vspeed[j];
            xnew = x + speed*sin(dpsi * M_PI/180 + psi*M_PI/180)*dt;
            ynew = y + speed*cos(dpsi * M_PI/180 + psi*M_PI/180)*dt;
            znew = z + vs*dt;

            int totalNodes = nodeList->size();
            Node _child(this,totalNodes,xnew,ynew,znew,psi+dpsi,vs,2);
            _child.
            AddChild(_child);
            nodeList->push_back(_child);
        }
    }

}

bool Node::operator<(Node &B) {
    double val1 = g + h;
    double val2 = B.g + B.h;

    if (val1 < val2){
        return true;
    }else{
        return false;
    }
}

bool Node::operator!=(Node &B) {
    if (index != B.index){
        return true;
    }else{
        return false;
    }
}

