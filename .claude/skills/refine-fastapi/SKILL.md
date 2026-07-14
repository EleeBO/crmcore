---
name: refine-fastapi
description: Integration patterns for Refine.dev admin panels with FastAPI Python backends. Use when building CRUD admin interfaces with shadcn/ui and FastAPI.
---

# Refine + FastAPI Integration

**Core Rule:** Refine handles frontend CRUD, FastAPI handles backend API. Data provider bridges them.

## When to Use

- Building admin panels with CRUD operations
- Creating dashboards with data tables
- Integrating React frontend with FastAPI backend
- Using shadcn/ui components with Refine

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Refine)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │  useList    │  │  useCreate  │  │  useUpdate      │  │
│  │  useOne     │  │  useDelete  │  │  useMany        │  │
│  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘  │
│         │                │                   │           │
│         └────────────────┼───────────────────┘           │
│                          ▼                               │
│              ┌───────────────────────┐                   │
│              │    Data Provider      │                   │
│              │  (FastAPI Adapter)    │                   │
│              └───────────┬───────────┘                   │
└──────────────────────────┼──────────────────────────────┘
                           │ HTTP/REST
┌──────────────────────────┼──────────────────────────────┐
│                          ▼                               │
│              ┌───────────────────────┐                   │
│              │      FastAPI          │                   │
│              │   (REST Endpoints)    │                   │
│              └───────────┬───────────┘                   │
│                          │                               │
│              ┌───────────▼───────────┐                   │
│              │    SQLAlchemy ORM     │                   │
│              │     (PostgreSQL)      │                   │
│              └───────────────────────┘                   │
│                    Backend (Python)                      │
└──────────────────────────────────────────────────────────┘
```

## FastAPI Backend Patterns

### Standard CRUD Endpoint Structure

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from pydantic import BaseModel

router = APIRouter(prefix="/users", tags=["users"])

# Response schemas for Refine
class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    status: str
    created_at: datetime

class PaginatedResponse(BaseModel):
    items: List[UserResponse]
    total: int

# LIST - getList() in Refine
@router.get("", response_model=PaginatedResponse)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = "asc",
    # Filters
    status: Optional[str] = None,
    role: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List users with pagination, sorting, and filtering."""
    query = select(User)

    # Apply filters
    if status:
        query = query.where(User.status == status)
    if role:
        query = query.where(User.role == role)
    if search:
        query = query.where(
            or_(User.name.ilike(f"%{search}%"), User.email.ilike(f"%{search}%"))
        )

    # Get total count
    total = await db.scalar(select(func.count()).select_from(query.subquery()))

    # Apply sorting
    if sort_by:
        order_col = getattr(User, sort_by, User.id)
        query = query.order_by(order_col.desc() if sort_order == "desc" else order_col)

    # Apply pagination
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    items = result.scalars().all()

    return PaginatedResponse(items=items, total=total)

# GET ONE - getOne() in Refine
@router.get("/{id}", response_model=UserResponse)
async def get_user(id: int, db: AsyncSession = Depends(get_db)):
    """Get single user by ID."""
    user = await db.get(User, id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# CREATE - create() in Refine
@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create new user."""
    user = User(**data.model_dump())
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

# UPDATE - update() in Refine
@router.put("/{id}", response_model=UserResponse)
async def update_user(
    id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update existing user."""
    user = await db.get(User, id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user

# DELETE - deleteOne() in Refine
@router.delete("/{id}")
async def delete_user(id: int, db: AsyncSession = Depends(get_db)):
    """Delete user (soft delete recommended)."""
    user = await db.get(User, id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Soft delete
    user.deleted_at = datetime.utcnow()
    await db.commit()

    return {"id": id}

# BULK GET - getMany() in Refine
@router.get("/bulk", response_model=List[UserResponse])
async def get_many_users(
    ids: str = Query(..., description="Comma-separated IDs"),
    db: AsyncSession = Depends(get_db),
):
    """Get multiple users by IDs."""
    id_list = [int(i) for i in ids.split(",")]
    result = await db.execute(select(User).where(User.id.in_(id_list)))
    return result.scalars().all()
```

## Refine Data Provider for FastAPI

```typescript
// src/providers/fastapi-provider.ts
import { DataProvider, HttpError } from "@refinedev/core";
import axios, { AxiosInstance } from "axios";

export const createFastAPIProvider = (apiUrl: string): DataProvider => {
  const client: AxiosInstance = axios.create({
    baseURL: apiUrl,
    headers: { "Content-Type": "application/json" },
  });

  // Error interceptor for FastAPI validation errors
  client.interceptors.response.use(
    (response) => response,
    (error) => {
      const customError: HttpError = {
        message: error.response?.data?.detail || error.message,
        statusCode: error.response?.status || 500,
        errors: error.response?.data?.errors,
      };
      return Promise.reject(customError);
    }
  );

  return {
    getApiUrl: () => apiUrl,

    // LIST with pagination, sorting, filtering
    getList: async ({ resource, pagination, filters, sorters, meta }) => {
      const { current = 1, pageSize = 10 } = pagination ?? {};

      const params: Record<string, any> = {
        skip: (current - 1) * pageSize,
        limit: pageSize,
      };

      // Handle sorting
      if (sorters && sorters.length > 0) {
        params.sort_by = sorters[0].field;
        params.sort_order = sorters[0].order;
      }

      // Handle filters
      filters?.forEach((filter) => {
        if ("field" in filter && filter.value !== undefined) {
          params[filter.field] = filter.value;
        }
      });

      const { data } = await client.get(`/${resource}`, { params });

      return {
        data: data.items,
        total: data.total,
      };
    },

    // GET ONE
    getOne: async ({ resource, id }) => {
      const { data } = await client.get(`/${resource}/${id}`);
      return { data };
    },

    // CREATE
    create: async ({ resource, variables }) => {
      const { data } = await client.post(`/${resource}`, variables);
      return { data };
    },

    // UPDATE
    update: async ({ resource, id, variables }) => {
      const { data } = await client.put(`/${resource}/${id}`, variables);
      return { data };
    },

    // DELETE
    deleteOne: async ({ resource, id }) => {
      const { data } = await client.delete(`/${resource}/${id}`);
      return { data };
    },

    // BULK GET
    getMany: async ({ resource, ids }) => {
      const { data } = await client.get(`/${resource}/bulk`, {
        params: { ids: ids.join(",") },
      });
      return { data };
    },
  };
};
```

## Refine App Setup with shadcn/ui

```typescript
// src/App.tsx
import { Refine } from "@refinedev/core";
import routerProvider from "@refinedev/react-router";
import { BrowserRouter, Routes, Route } from "react-router";
import { createFastAPIProvider } from "./providers/fastapi-provider";

// Resources
import { UserList, UserCreate, UserEdit, UserShow } from "./pages/users";

function App() {
  return (
    <BrowserRouter>
      <Refine
        dataProvider={createFastAPIProvider(import.meta.env.VITE_API_URL)}
        routerProvider={routerProvider}
        resources={[
          {
            name: "users",
            list: "/users",
            create: "/users/create",
            edit: "/users/edit/:id",
            show: "/users/show/:id",
          },
        ]}
      >
        <Routes>
          <Route path="/users" element={<UserList />} />
          <Route path="/users/create" element={<UserCreate />} />
          <Route path="/users/edit/:id" element={<UserEdit />} />
          <Route path="/users/show/:id" element={<UserShow />} />
        </Routes>
      </Refine>
    </BrowserRouter>
  );
}
```

## Data Table with shadcn/ui

```typescript
// src/pages/users/list.tsx
import { useTable } from "@refinedev/react-table";
import { ColumnDef, flexRender, getCoreRowModel } from "@tanstack/react-table";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const UserList = () => {
  const columns: ColumnDef<User>[] = [
    { accessorKey: "id", header: "ID" },
    { accessorKey: "name", header: "Name" },
    { accessorKey: "email", header: "Email" },
    { accessorKey: "role", header: "Role" },
    {
      id: "actions",
      cell: ({ row }) => (
        <div className="flex gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link to={`/users/edit/${row.original.id}`}>Edit</Link>
          </Button>
          <DeleteButton recordItemId={row.original.id} />
        </div>
      ),
    },
  ];

  const { getHeaderGroups, getRowModel, setFilters } = useTable({
    columns,
    refineCoreProps: {
      resource: "users",
      pagination: { pageSize: 10 },
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex justify-between">
        <Input
          placeholder="Search..."
          onChange={(e) => setFilters([{ field: "search", value: e.target.value }])}
          className="max-w-sm"
        />
        <Button asChild>
          <Link to="/users/create">Create User</Link>
        </Button>
      </div>

      <Table>
        <TableHeader>
          {getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id}>
                  {flexRender(header.column.columnDef.header, header.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {getRowModel().rows.map((row) => (
            <TableRow key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
};
```

## Form with react-hook-form + zod

```typescript
// src/pages/users/create.tsx
import { useForm } from "@refinedev/react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const userSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters"),
  email: z.string().email("Invalid email address"),
  role: z.enum(["admin", "manager", "user"]),
});

export const UserCreate = () => {
  const {
    refineCore: { onFinish, formLoading },
    ...form
  } = useForm({
    resolver: zodResolver(userSchema),
    defaultValues: { name: "", email: "", role: "user" },
  });

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onFinish)} className="space-y-4">
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Name</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Email</FormLabel>
              <FormControl>
                <Input type="email" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="role"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Role</FormLabel>
              <Select onValueChange={field.onChange} defaultValue={field.value}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Select role" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="manager">Manager</SelectItem>
                  <SelectItem value="user">User</SelectItem>
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        <Button type="submit" disabled={formLoading}>
          {formLoading ? "Creating..." : "Create User"}
        </Button>
      </form>
    </Form>
  );
};
```

## Project Structure

```
project/
├── backend/                    # FastAPI
│   ├── src/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── users.py    # CRUD endpoints
│   │   │       └── orders.py
│   │   ├── models/
│   │   │   └── user.py         # SQLAlchemy models
│   │   ├── schemas/
│   │   │   └── user.py         # Pydantic schemas
│   │   └── main.py
│   └── pyproject.toml
│
├── frontend/                   # Refine + shadcn
│   ├── src/
│   │   ├── components/ui/      # shadcn components
│   │   ├── pages/
│   │   │   └── users/
│   │   │       ├── list.tsx
│   │   │       ├── create.tsx
│   │   │       ├── edit.tsx
│   │   │       └── show.tsx
│   │   ├── providers/
│   │   │   └── fastapi-provider.ts
│   │   └── App.tsx
│   └── package.json
│
└── docker-compose.yml
```

## Checklist for New CRUD Entity

- [ ] **Backend:**
  - [ ] SQLAlchemy model in `models/`
  - [ ] Pydantic schemas (Create, Update, Response)
  - [ ] CRUD router with all 5 operations
  - [ ] Register router in `main.py`
  - [ ] Write tests

- [ ] **Frontend:**
  - [ ] Add resource to Refine config
  - [ ] Create List page with data table
  - [ ] Create Create page with form
  - [ ] Create Edit page with form
  - [ ] Create Show page (optional)
  - [ ] Add routes

## Resources

- [Refine Documentation](https://refine.dev/docs/)
- [shadcn/ui](https://ui.shadcn.com/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [shadcn-admin-kit](https://github.com/marmelab/shadcn-admin-kit)
