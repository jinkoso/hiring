# Jinko Full-Stack Interview Assignment

## Introduction

At Jinko, our engineers work on products that combine thoughtful architecture with solid implementation. We value people who can understand the **business context**, design a solution that fits the needs, and then bring it to life in code.

For this exercise, you will create **Jinko Mini-Shop** — a simplified version of an e-commerce platform. We want to give you as much background information as possible so you can approach the task in your own way. There’s no fixed method — you’re free to decide how to design and implement it. What we care about is clarity, reasoning, and working results.

---

## Business Context

Imagine Jinko is launching a small online shop to test a new market. This shop will:

* Showcase products (only those marked as “visible”)
* Let customers add products to a shopping cart, update quantities, and view a checkout summary
* Let an admin user (or anyone with the link) manage products — create, edit, delete, and hide/show them

The shop should have three main views:

1. **Welcome Page** — a simple landing page introducing the shop with navigation links.
2. **Product Admin (CRUD)** — for managing products, including name, price, description, visibility, and stock.
3. **Storefront & Cart (CRUD)** — for browsing visible products and managing a shopping cart.

---

## Data Model (Baseline)

**Product**

* id
* name
* price
* description
* visible (boolean)
* stock (integer)
* created\_at / updated\_at

**CartItem**

* id
* product\_id
* quantity
* unit\_price (captured at time of adding to cart)

---

## Technical Expectations

You may implement the solution in any style you see fit, but the following is our tech stack:

* **Back-End**: Golang (Gin/Chi/Fiber) with PostgreSQL or MySQL
* **Front-End**: React + TypeScript
* **Optional**: Use Docker for easier setup, migrations for DB schema, and Redux Toolkit/Zustand for state management

We expect:

Build a Basic Shop web application with 3 pages.
 - **Basic Shop home page** is a static welcome page with links to the admin and customer pages.
 - **Admin view** is a CRUD interface where admins (or anyone who click on that link) can creat, list, modify products.
 - **Shop and cart view** is a CRUD interface for Shopping Cart plus it list only visible products.

### We have only one task, but with options for Full Stack, Back-End and Front-End.
### A Front-End developer may use localStorage and focus on the user interface, meanwhile a Back-End developer may done with RESTful-API endpoint only. Naturally a Full Stack folk should be able to progress on both side.

### Back-End must have
 - Build a working web application on Golang and relational DB
 - Endpoints to manage products
 - Endpoints to manage cart
 - A README.md telling how it works.

### Back-End Nice to Have
 - Clear project structure and readable code style
 - DB migration files
 - Usages of Docker or a cloud platform
 - Comment or Documentation in clear English for Front-End developer as SLA

### Front-End must have
 - Build a Single-page Application website
 - Back-End can be mocked using [Json-Server][Json-Server]
 - A view to manage products.
 - A view to manage cart.
 - A README.md telling how it works.

### Front-End Nice to Have
 - View separation with Router
 - Good demonstration of state management
 - Clear project structure and readable code style
 - Demonstration usage of Babel and LESS/SASS/SCSS
 - Clear demonstration of stateless and stateful components
 - Comment or Documentation in clear English for Back-End developer as SLA

### Front-End bonus
 - Utilization of [Ant Design][AntDesign] or any of the resources listed [HERE][awesome]
 - Utilization of [Alibaba DvaJS][DvaJS]
 - Unit testing
 - Usage of best practices such as BEM, DRY


### Full Stack must have
 - All the must have of Front- and Back-End

### Full Stack should have
 - All the should have of Front- and Back-End

---

## What We Value in Your Submission

* **Business understanding** — does your solution fit the scenario we described?
* **Clarity of architecture** — is your structure easy to understand and reason about?
* **Code quality** — readability, maintainability, and sensible structure
* **Correctness** — CRUD operations work as expected, cart calculations are accurate
* **Documentation** — README that helps another developer run and understand your project
* **Scalability & security thinking** — even if you don’t fully implement them, show us you’ve considered them

---

## Deliverables

Push your work to a public GitHub repository including:

* Your code
* A **README.md** explaining:

  * Overview of your solution
  * How to run it locally
  * API documentation or usage examples
  * Any assumptions you made
  * Known limitations and possible improvements

---

## Tips

* Use any AI tools to help your work.
* Build an MVP first — working end-to-end functionality is better than a half-built large system.
* Use whatever diagrams or notes help communicate your design.
* Document trade-offs you make — we know time is limited.
* Treat this as if you were delivering to a real client at Jinko.

Good luck — we’re looking forward to seeing your approach!
