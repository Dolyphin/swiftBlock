# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

'''
'''

import mathutils,time
import numpy as np

# Writes blockMeshDict to provided path
def write(filepath, edges, vertices_coord, convertToMeters, patchnames, polyLines, edgeInfo, vertexNames, disabled, logging,stime):
    if logging:
        logFileName = filepath.replace('blockMeshDict','log.swiftblock')
        debugFileName = filepath.replace('blockMeshDict','facesFound.obj')
    else:
        logFileName = ''
        debugFileName = ''
    
    patchfaces = []
    for pn in patchnames:
        for vl in pn[2]:
            patchfaces.append(vl)
    # Get the blockstructure, which edges that have the same #of cells, some info on face, and edges-in-use
    logFile, block_print_out, dependent_edges, face_info, all_edges, faces_as_list_of_nodes = blockFinder(edges, vertices_coord, logFileName, debugFileName, disabled)
    bmFile = open(filepath,'w')
    bmFile.write(foamHeader())
    bmFile.write("\nconvertToMeters " + str(convertToMeters) + ";\n\nvertices\n(\n")
    
    for v in vertices_coord:
        bmFile.write('    ({} {} {})\n'.format(*v))
    bmFile.write(");\nblocks\n(\n")
    
    # Get the directions of the parallel edges
    edgeDirections = getEdgeDirections(dependent_edges,block_print_out,edgeInfo)
    
    # Loop through all blocks and get resolution and grading and write to file
    NoCells = 0
    for bid, vl in enumerate(block_print_out):
        blockName = ''
        for name in reversed(vertexNames):
            if all( v in name[1] for v in vl ):
                blockName = name[0]
                
        for es, edgeSet in enumerate(dependent_edges):
            if edge(vl[0],vl[1]) in edgeSet:
                iedges = [(vl[e[0]],vl[e[1]]) for e in [(0,1),(3,2),(7,6),(4,5)]]
                ires,igrad = getGrading(iedges,edgeSet,edgeInfo, iedges[0] in edgeDirections[es])
                
            if edge(vl[0],vl[3]) in edgeSet:
                jedges = [(vl[e[0]],vl[e[1]]) for e in [(0,3),(1,2),(5,6),(4,7)]]
                jres,jgrad = getGrading(jedges,edgeSet,edgeInfo,jedges[0] in edgeDirections[es])

            if edge(vl[0],vl[4]) in edgeSet:
                kedges = [(vl[e[0]],vl[e[1]]) for e in [(0,4),(1,5),(2,6),(3,7)]]
                kres,kgrad = getGrading(kedges,edgeSet,edgeInfo,kedges[0] in edgeDirections[es])
                              
        NoCells += ires*jres*kres
        bmFile.write('// block id {} \nhex ({} {} {} {} {} {} {} {}) '.format(bid,*vl) \
                   + blockName + ' ({} {} {}) '.format(ires,jres,kres)\
                   + 'edgeGrading (' + igrad + jgrad + kgrad + '\n)\n' ) 
        
    bmFile.write(');\n\npatches\n(\n')
    for pn in patchnames:
        if not len(pn[2]) == 0:
            bmFile.write('    {} {}\n    (\n'.format(pn[0],pn[1]))
            for pl in pn[2]:
                fid, tmp = findFace(faces_as_list_of_nodes, pl)
                if fid >= 0:
                    if (len(face_info[fid]['neg']) + len(face_info[fid]['pos'])) == 1: #avoid printing internal faces and patches in non-identified blocks as patch
                        bmFile.write('        ({} {} {} {})\n'.format(*pl))
            bmFile.write('    )\n')
            
    bmFile.write(');\n\nedges\n(\n')
    for pl in polyLines:
        bmFile.write(pl)     
    bmFile.write(foamFileEnd())
    bmFile.close()
    return NoCells


def getEdgeDirections(dependent_edges, block_print_out, edgeInfo):
    edgeDirections = [set() for i in dependent_edges]               
    positiveBlockEdges = [[(0,1),(3,2),(7,6),(4,5)],[(0,3),(1,2),(5,6),(4,7)],[(0,4),(1,5),(2,6),(3,7)]]
    for i in range(1000):
        ready = True
        for ed, de in zip(edgeDirections,dependent_edges):
            if not len(ed)==len(de):
                ready = False
        if ready:
            break 
        for bid, vl in enumerate(block_print_out):
            for es, edgeSet in enumerate(dependent_edges):
                for direction in range(3):
                    if edge(vl[positiveBlockEdges[direction][0][0]],vl[positiveBlockEdges[direction][0][1]]) in edgeSet:  
                        if not edgeDirections[es]:                             
                            edgeDirections[es] = set([(vl[e[0]],vl[e[1]]) for e in positiveBlockEdges[direction]])
                        else:
                            simedges = edgeDirections[es].intersection([(vl[e[0]],vl[e[1]]) for e in positiveBlockEdges[direction]])
                            if simedges:
                                edgeDirections[es] |= set([(vl[e[0]],vl[e[1]]) for e in positiveBlockEdges[direction]])
                            else:
                                asimedges= set(edgeDirections[es]).intersection([(vl[e[1]],vl[e[0]]) for e in positiveBlockEdges[direction]])
                                if asimedges:
                                    edgeDirections[es] |= set([(vl[e[1]],vl[e[0]]) for e in positiveBlockEdges[direction]])
                                    
    # make sure that the gradings of the last modified edges are respected                               
    for idx,(ed,es) in enumerate(zip(edgeDirections,dependent_edges)):
        iedge = np.argmax([edgeInfo[(e[0],e[1])].time for e in es])
        depEdge = (es[iedge][0],es[iedge][1])
        if depEdge in edgeDirections[idx]:
            edgeDirections[idx] = set([(e[1],e[0]) for e in edgeDirections[idx]])  
    return edgeDirections               
                    
def getGrading(edges, dependent_edges, edgeInfo, changeDirection):
    #Get the number of cells from edge which has been most recent modified
    iedge = np.argmax([edgeInfo[(e[0],e[1])].time for e in dependent_edges])
    depEdge = edgeInfo[(dependent_edges[iedge][0],dependent_edges[iedge][1])]
    cells, grading = getGradingStr(depEdge,changeDirection)
    
    gradingStr = ''   
    if depEdge.copyAligned:
        for edge in edges:
            gradingStr += grading
    else:
        for edge in edges:
            edgei = edgeInfo[edge[0],edge[1]]
            cellse, grading = getGradingStr(edgei,False)
            gradingStr += grading   
    return cells, gradingStr

def getGradingStr(edge, changeDirection):
    controlby='MAX CELL SIZE'
    if edge.dx1 and not (edge.exp1-1) < 1e-6:
        n1=np.log(edge.maxdx/edge.dx1)/np.log(edge.exp1)
        l1=edge.dx1*(1-edge.exp1**n1)/(1-edge.exp1)
        ratio1 = edge.maxdx/edge.dx1
    else:
        n1=0
        l1=0
        ratio1=1
        
    if edge.dx2 and not (edge.exp2-1) < 1e-6:
        n2=np.log(edge.maxdx/edge.dx2)/np.log(edge.exp2)
        l2=edge.dx2*(1-edge.exp2**n2)/(1-edge.exp2) 
        ratio2 = edge.maxdx/edge.dx2
    else:
        n2=0
        l2=0
        ratio2=1 
        

    if l1 + l2 > edge.length :
        # if length is too short, increase expansion ratio
        if controlby == 'EXPANSION RATIO':
            l1=edge.length*l1/(l1+l2)
            l2=edge.length-l1
            if l1 and edge.dx1:
                n1=np.log(edge.maxdx/edge.dx1)/np.log(1-edge.dx1/l1+edge.maxdx/l1)
            else:
                n1=0
            if l2 and edge.dx2:
                n2=np.log(edge.maxdx/edge.dx2)/np.log(1-edge.dx2/l2+edge.maxdx/l2)
            else:
                n2=0

        # if length is too short, decrease the size of the max cell.
        elif l1 + l2 > edge.length and controlby == 'MAX CELL SIZE':
            l1=edge.length*l1/(l1+l2)
            l2=edge.length-l1
    
            if edge.dx1 and not (edge.exp1-1) < 1e-6:
                n1 = np.log(1-l1/edge.dx1*(1-edge.exp1))/np.log(edge.exp1)
                ratio1 = edge.exp1**n1
                
            if edge.dx2 and not (edge.exp2-1) < 1e-6:
                n2 = np.log(1-l2/edge.dx2*(1-edge.exp2))/np.log(edge.exp2)
                ratio2 = edge.exp2**n2
        else:
             print('Too short edge has not been taken into account')
    if edge.maxdx == 0:
        edge.maxdx = 1
    cells=np.round(((edge.length-l1-l2)/edge.maxdx))+n1+n2

    if cells < 1:
        cells=1
        
    l1s = l1/edge.length
    n1s = n1/cells
    l2s = l2/edge.length
    n2s = n2/cells
    
    lc = max(1-l1s-l2s,0)
    nc = max(1-n1s-n2s,0)     
            
    
    if lc == 0 or nc == 0:
        nc = lc = 0
        
    if changeDirection:
        n1s,n2s = n2s,n1s
        l1s,l2s = l2s,l1s
        ratio1,ratio2 = ratio2,ratio1
    gradingStr='\n(\n ({:.6g} {:.6g} {:.6g}) ({:.6g} {:.6g} {:.6g}) ({:.6g} {:.6g} {:.6g}) '.format(
            l1s,n1s,ratio1,\
            lc,nc,1,\
            l2s,n2s,1/ratio2) + '\n)'   

    return int(np.round(cells)), gradingStr
    
def repairFaces(edges, vertices_coord, disabled, obj, removeInternal, createBoundary):
    import bpy

    # Get the blockstructure, which edges that have the same #of cells, some info on face, and edges-in-use
    logFile, block_print_out, dependent_edges, face_info, all_edges, faces_as_list_of_nodes = blockFinder(edges, vertices_coord, '','', disabled)

    bpy.ops.wm.context_set_value(data_path="tool_settings.mesh_select_mode", value="(False,False,True)")

    nRemoved = 0
    if removeInternal:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        for f in obj.data.polygons:
            fid, tmp = findFace(faces_as_list_of_nodes, f.vertices)
            if fid >= 0: # face was found in list
                if (len(face_info[fid]['neg']) + len(face_info[fid]['pos'])) > 1: #this is an internal face
                    f.select = True
                    nRemoved += 1
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.delete(type='ONLY_FACE')
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')

    nCreated = 0
    if createBoundary:
        bpy.ops.wm.context_set_value(data_path="tool_settings.mesh_select_mode", value="(True,False,False)")
        presentFaces = []

        for f in obj.data.polygons:
            presentFaces.append(list(f.vertices))

        for faceid, f in enumerate(faces_as_list_of_nodes):
            if (len(face_info[faceid]['neg']) + len(face_info[faceid]['pos'])) == 1: #this is a boundary face
                fid, tmp = findFace(presentFaces, f)
                if fid < 0: # this boundary face does not exist as a blender polygon. lets create one!
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='DESELECT')
                    bpy.ops.object.mode_set(mode='OBJECT')
                    for v in f:
                        obj.data.vertices[v].select = True
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.edge_face_add()
                    bpy.ops.mesh.tris_convert_to_quads(limit=3.14159, uvs=False, vcols=False, sharp=False, materials=False)
                    nCreated += 1
    
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    return nRemoved, nCreated


def removedup(seq): 
    checked = []
    for e in seq:
        if e not in checked:
            checked.append(e)
    return checked
    
def edge(e0, e1):
    return [min(e0,e1), max(e0,e1)]
    
def couple_edges(dependent_edges):
    for es0, edgeSet0 in enumerate(dependent_edges):
        for edge in edgeSet0:
            for es1, edgeSet1 in enumerate(dependent_edges):
                if edge in edgeSet1 and es0 != es1:
                    for e in edgeSet0:
                        edgeSet1.append(e)
                    dependent_edges.pop(es0)
                    return True
    return False



def findFace(faces, vl):
    for fid, f in enumerate(faces):
        if vl[0] in f and vl[1] in f and vl[2] in f and vl[3] in f:
            return fid, f
    return -1, []


class cycleFinder:
# Credit: Adam Gaither. An Efficient Block Detection Algorithm For Structured Grid Generation
# 
    def __init__(self, edges, verts):
        self.edges = edges
        self.verticesId = verts
        self.edgeVisited = [False for i in range(len(edges))]
        self.currentCycle = []
        self.currentCycleEdges = []
        self.faces = []
        self.facesEdges = []
        self.facesId = []
        self.no_edges = 0
        self.v_in_edge = [[] for i in range(len(verts))]
        for v in verts:
            append = self.v_in_edge[v].append
            for eid, e in enumerate(self.edges):
                if v in e:
                    append(eid)

    def buildAllFourEdgeFaces(self):
        for v in self.verticesId:
            self.currentCycle = []
            self.currentCycleEdges = []
            self.currentCycle.append(v)
            self.buildFourEdgeFaces(v)
            self.VisitAllEdgeAdjacent(v)
        return self.faces,self.facesEdges

    def buildFourEdgeFaces(self, v):
        for eid in self.v_in_edge[v]:
            if not self.edgeVisited[eid]:
                e = self.edges[eid]
                self.no_edges += 1
                self.edgeVisited[eid] = True
                opposite_v = e[0]
                if opposite_v == v: # seems the other vertex is in e[1]!
                    opposite_v = e[1]
                self.currentCycle.append(opposite_v)
                self.currentCycleEdges.append(eid)
                if self.currentCycle[0] == self.currentCycle[-1]: # First equals last -> we have a face
                     if self.uniqueCycle():
                         self.faces.append(self.currentCycle[0:-1])
                         self.facesEdges.append(self.currentCycleEdges[:])
                         self.facesId.append(self.currentCycle[0:-1])
                         self.facesId[-1].sort()
                else:
                    if self.no_edges < 4:
                        self.buildFourEdgeFaces(opposite_v)
                self.no_edges -= 1
                self.currentCycle.pop()
                self.currentCycleEdges.pop()
                self.edgeVisited[eid] = False

    def uniqueCycle(self):
        cF = self.currentCycle[0:-1]
        cF.sort()
        return not cF in self.facesId
        
    def VisitAllEdgeAdjacent(self, v):
        for eid, e in enumerate(self.edges):
            if v in e:
                self.edgeVisited[eid]


def blockFinder(edges, vertices_coord, logFileName='', debugFileName='', disabled = []):
    stime = time.time()
    if len(logFileName) > 0:
        logFile = open(logFileName,'w')
    else:
        logFile = ''

    # Use the cycle finder class to find all edges forming quad faces
    cycFindFaces = cycleFinder(edges,range(len(vertices_coord)))
    faces_as_list_of_vertices = []
    faces_as_list_of_nodes = []
    faces_as_list_of_edges = []
    tmp_v,tmp_e = cycFindFaces.buildAllFourEdgeFaces()
    for ii, i in enumerate(tmp_v): # get rid of possible triangles
        if len(i) == 4:
            faces_as_list_of_vertices.append([vertices_coord[i[0]], vertices_coord[i[1]], vertices_coord[i[2]], vertices_coord[i[3]]])
            faces_as_list_of_nodes.append(i)
            faces_as_list_of_edges.append(tmp_e[ii])
    # Create a wavefront obj file showing all the faces just found
    if len(debugFileName) > 0:
        debugFile = open(debugFileName,'w')
        for v in vertices_coord:
            debugFile.write('v {} {} {}\n'.format(*v))
        for f in faces_as_list_of_nodes:
            debugFile.write('f ')
            for n in f:
                debugFile.write('{} '.format(n+1))
            debugFile.write('\n')
        debugFile.close()
    
    # Store some info for the faces in a dict
    face_info = {}
    for fid, f in enumerate(faces_as_list_of_vertices):
        normal = mathutils.geometry.normal(f[0],f[1],f[2],f[3])
        facecentre = mathutils.Vector((0,0,0))
        for v in f:
            facecentre += 0.25*v
        face_info[fid] = {}
        face_info[fid]['normal'] = normal
        face_info[fid]['pos'] = []
        face_info[fid]['neg'] = []
        face_info[fid]['centre'] = facecentre
        
    connections_between_faces = []
    # Find connections between faces, i.e. they share one edge
    for fid1, f1 in enumerate(faces_as_list_of_edges):
        for e in f1:
            for fid2, f2 in enumerate(faces_as_list_of_edges):
                if e in f2 and not fid1 == fid2:
                    if not [min(fid1,fid2),max(fid1,fid2)] in connections_between_faces:
                        connections_between_faces.append([min(fid1,fid2),max(fid1,fid2)])
   
    # Use these connections to find cycles of connected faces; called faceLoops 
    cycFindFaceLoops = cycleFinder(connections_between_faces,range(len(faces_as_list_of_vertices)))
    
    #this is the most time consuming step
    faceLoops_as_list_of_faces, faceLoops_as_list_of_connections = cycFindFaceLoops.buildAllFourEdgeFaces()
    # Dig out block structures from these face loops
    block_as_faceLoop = []
    for qf in faceLoops_as_list_of_faces:
        qf_is_a_block = True
        for n in faces_as_list_of_nodes[qf[0]]:
            if n in faces_as_list_of_nodes[qf[2]]: #if any of the vertices in face 0 is in face 2, this is not a block
                qf_is_a_block = False
        if qf_is_a_block:
            block_as_faceLoop.append(qf)
    # Get rid of block dublets - there are plenty
    faceLoops_nodes = [[] for i in range(len(block_as_faceLoop))]
    for qfid, qf in enumerate(block_as_faceLoop):
        for f in qf:
            for n in faces_as_list_of_nodes[f]:
                if not n in faceLoops_nodes[qfid]:
                    faceLoops_nodes[qfid].append(n)
    for qf in faceLoops_nodes:
        qf.sort()
    tmp = []
    potentialBlocks = [] # Each block is identified several times. Condense and put in potentialBlocks (list of vertices index)
    for qfid, qf in enumerate(faceLoops_nodes):
        if not qf in tmp:
            tmp.append(qf)
            if len(qf) == 8:
                potentialBlocks.append(block_as_faceLoop[qfid])
    offences = []
    block_centres = []
    formalBlocks = []
    dependent_edges = []
    all_edges = []
    if len(logFileName) > 0:
        logFile.write('number of potential blocks identified = ' + str(len(potentialBlocks)) + '\n')
       
    for b in potentialBlocks:
        is_a_real_block = True  # more sanity checks soon...
        block = []
        for n in faces_as_list_of_nodes[b[0]]:
            block.append(n)
        for n in faces_as_list_of_nodes[b[2]]:
            block.append(n)
        q2start = None
        for e in edges: # Locate the vertex just above block[0]. Store as q2start
            if block[0] == e[0]:
                if e[1] in block[4:8]:
                    q2start = block.index(e[1])
            if block[0] == e[1]:
                if e[0] in block[4:8]:
                    q2start = block.index(e[0])
        if q2start == None: # if not found above - this is not a complete block.
            q1nodes = block[0:4]
            q2nodes = block[4:-1]
            if len(logFileName) > 0:
                logFile.write('one block found was incomplete! ' + str(q1nodes) + str(q2nodes) + '\n')
            continue
            q2start = 0 #just set it to something. block wont be printed anyway
        quad1 = block[0:4]
        quad2 = []
        for i in range(4):
            quad2.append(block[(i + q2start) % 4 + 4])
        q1verts = [vertices_coord[quad1[0]],vertices_coord[quad1[1]],vertices_coord[quad1[2]],vertices_coord[quad1[3]]]
        q2verts = [vertices_coord[quad2[0]],vertices_coord[quad2[1]],vertices_coord[quad2[2]],vertices_coord[quad2[3]]]
        
        blockcentre = mathutils.Vector((0,0,0))
        for n in block:
            blockcentre += 0.125*vertices_coord[n]
        q1fid, tmp = findFace(faces_as_list_of_nodes, quad1)
        q2fid, tmp = findFace(faces_as_list_of_nodes, quad2)

        normal1 = mathutils.geometry.normal(*q1verts)
        normal2 = mathutils.geometry.normal(*q2verts)

        facecentre1 = face_info[q1fid]['centre']
        facecentre2 = face_info[q2fid]['centre']
        direction1 = blockcentre-facecentre1
        direction2 = blockcentre-facecentre2

        v04 = q2verts[0] - q1verts[0]
        scalarProd1 = direction1.dot(normal1)
        scalarProd2 = direction2.dot(normal2)
        scalarProd3 = normal1.dot(v04)

        if scalarProd1*scalarProd2 > 0.: # make quad1 and quad2 rotate in the same direction
            quad2 = [quad2[0], quad2[-1], quad2[-2], quad2[-3]] 
            normal2 *= -1.0

        if scalarProd3 < 0.: # Maintain righthanded system in each block
            tmp = list(quad2)
            quad2 = list(quad1)        
            quad1 = tmp

        for nid,n in enumerate(quad1): #check that all edges are present
            if not (([n,quad2[nid]] in edges) or ([quad2[nid],n] in edges)):
                if len(logFileName) > 0:
                    logFile.write('one block did not have all edges! ' + str(quad1) + str(quad2) + '\n')
                is_a_real_block = False
                break
        if not is_a_real_block:
            continue
   # more sanity...
        scale = v04.magnitude * normal1.magnitude
        if (abs(scalarProd3/scale) < 0.01): # abs(sin(alpha)) < 0.01, where alpha is angle for normal1 and v04
            if len(logFileName) > 0:
                logFile.write('flat block ruled out!' + str(quad1) + str(quad2) + '\n')
            continue

        if is_a_real_block: # this write-out only works if blenders own vertex numbering starts at zero!! seems to work...
            offences.append(0)
            block_centres.append(blockcentre)

            vl = quad1 + quad2
            formalBlocks.append(vl) # list of verts defining the block in correct order
# formalBlocks are blocks that hava formal block structure and are not flat. Still in an O-mesh there are more formal
# blocks present than what we want. More filtering...

    for bid, vl in enumerate(formalBlocks):
        fs = []
        fs.append(vl[0:4])
        fs.append(vl[4:8])
        fs.append([vl[0], vl[1], vl[5], vl[4]])
        fs.append([vl[1], vl[2], vl[6], vl[5]])
        fs.append([vl[2], vl[3], vl[7], vl[6]])
        fs.append([vl[3], vl[0], vl[4], vl[7]])
        blockcentre = block_centres[bid]
        for f in fs:
            fid, tmp = findFace(faces_as_list_of_nodes, f)
            normal = face_info[fid]['normal']
            facecentre = face_info[fid]['centre']
            direction = normal.dot((blockcentre-facecentre))
            if direction >= 0.:
                face_info[fid]['pos'].append(bid)
            else:
                face_info[fid]['neg'].append(bid)
    for f in face_info:  # Not more than two blocks on each side of a face. If a block scores too high in 'offences' it will be ruled out
        if len(face_info[f]['pos'])>1:
            for bid in face_info[f]['pos']:
                offences[bid] += 1
        if len(face_info[f]['neg'])>1:
            for bid in face_info[f]['neg']:
                offences[bid] += 1
    block_print_out = []
    for bid, vl in enumerate(formalBlocks):
        if offences[bid] <= 3 and not all( v in disabled for v in vl ):
            block_print_out.append(vl)
            i_edges = [edge(vl[0],vl[1]), edge(vl[2],vl[3]), edge(vl[4],vl[5]), edge(vl[6],vl[7])]
            j_edges = [edge(vl[1],vl[2]), edge(vl[3],vl[0]), edge(vl[5],vl[6]), edge(vl[7],vl[4])]
            k_edges = [edge(vl[0],vl[4]), edge(vl[1],vl[5]), edge(vl[2],vl[6]), edge(vl[3],vl[7])]
#            i_edges = [[vl[0],vl[1]], [vl[2],vl[3]], [vl[4],vl[5]], [vl[6],vl[7]]]
#            j_edges = [[vl[1],vl[2]], [vl[3],vl[0]], [vl[5],vl[6]], [vl[7],vl[4]]]
#            k_edges = [[vl[0],vl[4]], [vl[1],vl[5]], [vl[2],vl[6]], [vl[3],vl[7]]]
            dependent_edges.append(i_edges) #these 4 edges have the same resolution
            dependent_edges.append(j_edges) #these 4 edges have the same resolution
            dependent_edges.append(k_edges) #these 4 edges have the same resolution
            for e in range(4):
                if not i_edges[e] in all_edges:
                    all_edges.append(i_edges[e])
                if not j_edges[e] in all_edges:
                    all_edges.append(j_edges[e])
                if not k_edges[e] in all_edges:
                    all_edges.append(k_edges[e])
        else:  # Dont let non-allowed blocks to stop definition of patch names
            for f in face_info:
                if bid in face_info[f]['pos']:
                    ind = face_info[f]['pos'].index(bid)
                    face_info[f]['pos'].pop(ind)
                if bid in face_info[f]['neg']:
                    ind = face_info[f]['neg'].index(bid)
                    face_info[f]['neg'].pop(ind)
    #this is the second most time consuming step
    still_coupling = True
    while still_coupling:
        still_coupling = couple_edges(dependent_edges)
        
    for es, edgeSet in enumerate(dependent_edges): # remove duplicates in lists
        dependent_edges[es] = removedup(edgeSet)
    return logFile, block_print_out, dependent_edges, face_info, all_edges, faces_as_list_of_nodes

def smootherProfile():
    return [-7.438494264988549e-15, 0.008605801693457149, 0.01842475807111854, 0.029612300648478973, 0.04233898400088343, 0.05679046185429426, 0.07316690916267587, 0.09168171542424897, 0.11255925232965769, 0.13603150492164162, 0.16233335611953192, 0.19169633764727423, 0.22434071509985654, 0.26046587000768784, 0.3002390841616158, 0.34378302306103725, 0.3911624496237259, 0.44237095781465174, 0.4973187660157523, 0.5558228055972574, 0.6176004265387395, 0.6822679660953321, 0.7493451518442462, 0.8182658327045534, 0.8883948904481273, 0.9590504652620432, 1.0295299509754288, 1.0991377055224336, 1.1672121827956488, 1.233150273303395, 1.2964270258686001, 1.3566095317190248, 1.413364466852664, 1.466459481809475, 1.51575919532818, 1.5612169266010856, 1.6028634731905456, 1.640794230426153, 1.6751558000542404, 1.7061330065249791, 1.7339369799788438, 1.7587947154353591, 1.780940303263625, 1.8006078588113952, 1.8180260609303134, 1.8334141352670894, 1.8469790804055504, 1.858913924091119, 1.8693968042865756, 1.8785906885314005, 1.8785906885314005, 1.8693968042865756, 1.8589139240911188, 1.8469790804055504, 1.8334141352670896, 1.8180260609303134, 1.8006078588113952, 1.7809403032636248, 1.7587947154353591, 1.733936979978844, 1.7061330065249791, 1.6751558000542404, 1.6407942304261525, 1.6028634731905456, 1.5612169266010856, 1.51575919532818, 1.4664594818094752, 1.4133644668526637, 1.3566095317190248, 1.2964270258685997, 1.233150273303395, 1.167212182795649, 1.0991377055224336, 1.0295299509754288, 0.9590504652620429, 0.8883948904481273, 0.8182658327045538, 0.7493451518442462, 0.6822679660953324, 0.6176004265387393, 0.5558228055972576, 0.49731876601575203, 0.44237095781465174, 0.39116244962372615, 0.3437830230610369, 0.3002390841616158, 0.2604658700076876, 0.22434071509985654, 0.19169633764727423, 0.16233335611953192, 0.13603150492164162, 0.11255925232965747, 0.09168171542424897, 0.07316690916267576, 0.05679046185429426, 0.04233898400088343, 0.029612300648478973, 0.01842475807111854, 0.008605801693457149, -7.438494264988549e-15]

def foamHeader():
    return """/*--------------------------------*- C++ -*----------------------------------*/

// File was generated by SwiftBlock, a Blender 3D addon.

FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""


def foamFileEnd():
    return """);

mergePatchPairs
(
);

// ************************************************************************* //
"""





